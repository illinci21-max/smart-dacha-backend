"""
FastAPI dependencies: auth, subscriptions, limits.

FIXES from Code Review:
  §1.2 CRITICAL — uses RedisManager instead of inline _get_redis()
  §1.3 HIGH    — fully async blacklist check (no more blocking event loop)
  §2.3 MEDIUM  — fail-CLOSED strategy: if Redis is down, reject token
                  (combined with short-lived access tokens = minimal window)
  §S-13        — subscription_expires_at=None means "no subscription"
  §R-03        — check_plants_limit filters by plot_id
"""
from datetime import datetime, timezone
from typing import Annotated
import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import jwt
from jwt import InvalidTokenError

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.plot import Plot
from app.models.plant import Plant
from app.services.redis_service import get_blacklist_redis

logger = logging.getLogger(__name__)
security = HTTPBearer()


# ── Async blacklist check (§1.3) ──────────────────────────────────────────────

async def _is_blacklisted(jti: str) -> bool:
    """
    Check if JWT ID is in the Redis blacklist.

    §2.3 FIX: fail-CLOSED — if Redis is unreachable, reject the token.
    Combined with short-lived access tokens (15 min), this is safe:
    even if Redis is down, tokens expire quickly.
    """
    try:
        r = await get_blacklist_redis()
        return bool(await r.get(f"blacklist:{jti}"))
    except Exception as exc:
        logger.error("Redis blacklist unavailable: %s — rejecting token (fail-closed)", exc)
        return True  # §2.3: fail-closed instead of fail-open


async def blacklist_token(jti: str, expires_minutes: int) -> None:
    """Add a JWT ID to the blacklist with TTL."""
    try:
        r = await get_blacklist_redis()
        await r.setex(f"blacklist:{jti}", expires_minutes * 60, "1")
    except Exception as exc:
        logger.warning("Failed to blacklist token jti=%s: %s", jti, exc)


# ── JWT decode ────────────────────────────────────────────────────────────────

async def decode_and_validate_token(token: str) -> dict:
    """
    Decode JWT, validate type and blacklist.

    §S-01: checks blacklist
    §S-10: rejects refresh tokens used as access
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалідний або прострочений токен",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # §S-10: reject refresh tokens
    if payload.get("type", "access") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалідний тип токена",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # §S-01: check blacklist (async!)
    jti = payload.get("jti")
    if jti and await _is_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Токен відкликано. Увійдіть знову.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


# ── Current user ──────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = await decode_and_validate_token(credentials.credentials)
    user_id: str = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Невалідний токен")

    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Користувача не знайдено")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# ── Subscription check ────────────────────────────────────────────────────────

def require_premium(feature: str = ""):
    """
    Dependency factory: checks Premium subscription.
    §S-13: subscription_expires_at=None → FREE (no active sub).
    """
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        now = datetime.now(timezone.utc)
        is_premium = current_user.subscription_tier in ("premium", "premium_plus")

        if is_premium:
            if current_user.subscription_expires_at is None:
                is_premium = False
            elif current_user.subscription_expires_at <= now:
                is_premium = False

        if not is_premium:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "premium_required",
                    "feature": feature,
                    "message": f"Функція '{feature}' доступна лише в Premium підписці",
                    "upgrade_url": "https://app.smartdacha.ua/upgrade",
                },
            )
        return current_user

    return _check


# ── Limit checks ──────────────────────────────────────────────────────────────

async def check_plots_limit(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    count = await db.scalar(
        select(func.count(Plot.id)).where(
            Plot.user_id == current_user.id,
            Plot.is_deleted.is_(False),
        )
    )
    if (count or 0) >= current_user.plots_limit:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "plots_limit_reached",
                "current": count,
                "limit": current_user.plots_limit,
                "message": "Досягнуто ліміт ділянок. Оновіть до Premium.",
            },
        )
    return current_user


async def check_plants_limit(
    plot_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    §R-03: count plants per plot_id, not per entire user.
    """
    # Verify plot belongs to user
    plot = await db.scalar(
        select(Plot).where(
            Plot.id == plot_id,
            Plot.user_id == current_user.id,
            Plot.is_deleted.is_(False),
        )
    )
    if not plot:
        raise HTTPException(status_code=404, detail="Ділянку не знайдено")

    count = await db.scalar(
        select(func.count(Plant.id)).where(
            Plant.plot_id == plot_id,
            Plant.is_deleted.is_(False),
        )
    )
    if (count or 0) >= current_user.plants_limit:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "plants_limit_reached",
                "current": count,
                "limit": current_user.plants_limit,
                "message": "Досягнуто ліміт рослин. Оновіть до Premium.",
            },
        )
    return current_user

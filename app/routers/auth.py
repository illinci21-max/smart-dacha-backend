"""
Auth Router — registration, login, JWT tokens.

FIXES from Code Review:
  §1.2 — uses dependencies.blacklist_token() (unified RedisManager)
  §2.3 — short-lived access tokens (15 min instead of 1440)
  §S-01 — JWT blacklist via Redis
  §S-04 — rate limiting via slowapi
  §S-10 — token type validation on refresh
"""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import jwt
from jwt import InvalidTokenError
import bcrypt

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    RegisterRequest, LoginRequest, TokenResponse,
    RefreshRequest, UserResponse, PasswordResetRequest,
    PasswordResetConfirmRequest,
)
from app.dependencies import get_current_user, blacklist_token
from app.services.email_service import send_password_reset_email
from app.services.subscription_service import TIER_LIMITS

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Rate limiting ─────────────────────────────────────────────────────────────
try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    limiter = Limiter(key_func=get_remote_address, storage_uri=settings.REDIS_URL)
    _has_limiter = True
except ImportError:
    limiter = None
    _has_limiter = False


def _rate_limit(limit_string: str):
    def decorator(func):
        if _has_limiter and limiter:
            return limiter.limit(limit_string)(func)
        return func
    return decorator


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def _password_reset_code_hash(user_id: str, code: str) -> str:
    message = f"{user_id}:{code}".encode("utf-8")
    secret = settings.SECRET_KEY.encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


# ── Token creation ────────────────────────────────────────────────────────────

def create_token(subject: str, expires_delta: timedelta, token_type: str = "access") -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": subject,
        "exp": expire,
        "type": token_type,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=201)
@_rate_limit("10/minute")
async def register(request: Request, data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(User).where(User.email == data.email))
    if existing:
        raise HTTPException(status_code=409, detail="Email вже зареєстровано")

    free_limits = TIER_LIMITS["free"]
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        plots_limit=free_limits["plots_limit"],
        plants_limit=free_limits["plants_limit"],
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _generate_tokens(str(user.id))


@router.post("/login", response_model=TokenResponse)
@_rate_limit("10/minute")
async def login(request: Request, data: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(
        select(User).where(User.email == data.email, User.is_active.is_(True))
    )
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невірний email або пароль",
        )
    return _generate_tokens(str(user.id))


@router.post("/refresh", response_model=TokenResponse)
@_rate_limit("20/minute")
async def refresh_token(request: Request, data: RefreshRequest):
    try:
        payload = jwt.decode(data.refresh_token, settings.SECRET_KEY, algorithms=["HS256"])

        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Невалідний refresh token")

        # Check blacklist (async)
        from app.services.redis_service import get_blacklist_redis
        jti = payload.get("jti")
        if jti:
            r = await get_blacklist_redis()
            if await r.get(f"blacklist:{jti}"):
                raise HTTPException(status_code=401, detail="Токен відкликано")

        return _generate_tokens(payload["sub"])
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Прострочений або невалідний токен")


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/logout", status_code=204)
async def logout(
    current_user: User = Depends(get_current_user),
    request: Request = None,
):
    """
    §1.2 FIX: uses dependencies.blacklist_token() (async, unified Redis).
    """
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            jti = payload.get("jti")
            if jti:
                await blacklist_token(jti, settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        except Exception:
            pass
    return None


@router.post("/password-reset", status_code=202)
@_rate_limit("5/minute")
async def request_password_reset(
    request: Request,
    data: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await db.scalar(
        select(User).where(User.email == data.email, User.is_active.is_(True))
    )
    if user:
        code = f"{secrets.randbelow(1_000_000):06d}"
        expires_minutes = 30
        user.password_reset_code_hash = _password_reset_code_hash(str(user.id), code)
        user.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=expires_minutes
        )
        await db.commit()
        await send_password_reset_email(user.email, code, expires_minutes)
    return {"message": "Якщо цей email зареєстровано — інструкції надіслано"}


@router.post("/password-reset/confirm")
@_rate_limit("10/minute")
async def confirm_password_reset(
    request: Request,
    data: PasswordResetConfirmRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await db.scalar(
        select(User).where(User.email == data.email, User.is_active.is_(True))
    )
    now = datetime.now(timezone.utc)
    invalid_error = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Невірний або прострочений код відновлення",
    )

    expires_at = user.password_reset_expires_at if user else None
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if (
        not user
        or not user.password_reset_code_hash
        or not expires_at
        or expires_at < now
    ):
        raise invalid_error

    expected_hash = _password_reset_code_hash(str(user.id), data.code)
    if not hmac.compare_digest(expected_hash, user.password_reset_code_hash):
        raise invalid_error

    user.password_hash = hash_password(data.new_password)
    user.password_reset_code_hash = None
    user.password_reset_expires_at = None
    await db.commit()
    return {"message": "Пароль оновлено"}


# ── Private ───────────────────────────────────────────────────────────────────

def _generate_tokens(user_id: str) -> TokenResponse:
    access_token = create_token(
        user_id, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    refresh_token = create_token(
        user_id,
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        token_type="refresh",
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

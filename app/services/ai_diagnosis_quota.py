"""Weekly AI diagnosis quota for Free tier users."""
from __future__ import annotations

import logging
from datetime import date

from fastapi import HTTPException

from app.config import settings
from app.models.user import User
from app.services.redis_service import get_cache_redis


logger = logging.getLogger(__name__)

_TTL_SECONDS = 15 * 24 * 3600


def _week_key(user_id: object) -> str:
    year, week, _ = date.today().isocalendar()
    return f"ai_diagnosis:weekly:{year}:w{week}:user:{user_id}"


async def check_and_consume_ai_diagnosis_quota(user: User) -> None:
    """Allow all tiers, but limit Free AI diagnosis to 3 per ISO week."""
    if user.subscription_tier != "free":
        return

    limit = settings.FREE_DIAGNOSES_PER_WEEK
    if limit <= 0:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "diagnosis_limit_reached",
                "used": 0,
                "limit": 0,
                "period": "week",
                "message": "AI-діагностика тимчасово недоступна для Free.",
            },
        )

    try:
        redis = await get_cache_redis()
        key = _week_key(user.id)
        used = await redis.incr(key)
        if used == 1:
            await redis.expire(key, _TTL_SECONDS)
    except Exception as exc:
        logger.error("AI diagnosis quota check failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail={
                "error": "quota_unavailable",
                "message": "Не вдалося перевірити ліміт AI-діагностики. Спробуйте пізніше.",
            },
        ) from exc

    if used > limit:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "diagnosis_limit_reached",
                "used": used - 1,
                "limit": limit,
                "period": "week",
                "message": f"Ліміт AI-діагностики для Free: {limit} звернення на тиждень.",
            },
        )

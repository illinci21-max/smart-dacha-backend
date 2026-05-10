"""Redis-backed Gemini usage counters for admin visibility."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from uuid import UUID

from app.services.redis_service import get_cache_redis


logger = logging.getLogger(__name__)

_RETENTION_DAYS = 32
_TTL_SECONDS = _RETENTION_DAYS * 24 * 3600


def _day_key(day: date) -> str:
    return day.isoformat()


async def record_gemini_usage(kind: str, user_id: UUID | str | None = None) -> None:
    """Record one outbound Gemini API attempt.

    Counters are intentionally best-effort: Gemini calls must not fail because
    usage telemetry is temporarily unavailable.
    """
    try:
        redis = await get_cache_redis()
        today = _day_key(date.today())
        keys = [
            f"gemini:usage:{today}:total",
            f"gemini:usage:{today}:kind:{kind}",
        ]
        if user_id is not None:
            user_key = str(user_id)
            keys.extend(
                [
                    f"gemini:usage:{today}:user:{user_key}:total",
                    f"gemini:usage:{today}:user:{user_key}:{kind}",
                ]
            )

        pipe = redis.pipeline()
        for key in keys:
            pipe.incr(key)
            pipe.expire(key, _TTL_SECONDS)
        if user_id is not None:
            pipe.zincrby(f"gemini:usage:{today}:users", 1, str(user_id))
            pipe.expire(f"gemini:usage:{today}:users", _TTL_SECONDS)
        await pipe.execute()
    except Exception as exc:
        logger.warning("Gemini usage counter failed: %s", exc)


async def get_gemini_usage_total(days: int = 1) -> int:
    """Return total Gemini attempts for the last N calendar days."""
    try:
        redis = await get_cache_redis()
        today = date.today()
        keys = [
            f"gemini:usage:{_day_key(today - timedelta(days=offset))}:total"
            for offset in range(max(1, days))
        ]
        values = await redis.mget(keys)
        return sum(int(value or 0) for value in values)
    except Exception as exc:
        logger.warning("Gemini total usage read failed: %s", exc)
        return 0


async def get_gemini_usage_by_user(days: int = 1, limit: int = 10) -> list[dict[str, int | str]]:
    """Return top users by Gemini attempts for the last N calendar days."""
    try:
        redis = await get_cache_redis()
        today = date.today()
        scores: dict[str, int] = {}
        for offset in range(max(1, days)):
            day = _day_key(today - timedelta(days=offset))
            rows = await redis.zrevrange(
                f"gemini:usage:{day}:users",
                0,
                max(0, limit * 3 - 1),
                withscores=True,
            )
            for user_id, score in rows:
                if isinstance(user_id, bytes):
                    user_id = user_id.decode("utf-8")
                scores[str(user_id)] = scores.get(str(user_id), 0) + int(score)

        top = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]
        return [{"user_id": user_id, "count": count} for user_id, count in top]
    except Exception as exc:
        logger.warning("Gemini per-user usage read failed: %s", exc)
        return []

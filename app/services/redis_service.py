"""
Unified Redis connection manager with connection pooling.

FIXES from Code Review:
  §1.2 CRITICAL — eliminates 3 duplicate _get_redis() functions
                  (was in auth.py, dependencies.py, weather_service.py)
  §1.3 HIGH    — provides async client for FastAPI (no more blocking event loop)

Architecture:
  - Async pools  → FastAPI routes (non-blocking)
  - Sync pools   → Celery workers (blocking OK in worker threads)
  - Each DB gets its own pool (max_connections controlled)

DB layout:
  0 — default / Celery result backend
  1 — JWT blacklist
  2 — weather cache flags
  3 — general cache
"""
from __future__ import annotations

import logging
from typing import ClassVar

import redis
import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

# ── DB constants (single source of truth) ─────────────────────────────────────
REDIS_DB_DEFAULT = 0
REDIS_DB_BLACKLIST = 1
REDIS_DB_WEATHER = 2
REDIS_DB_CACHE = 3


class RedisManager:
    """
    Singleton-style manager for both async and sync Redis clients.

    Usage (async — FastAPI):
        redis = await RedisManager.async_client(db=1)
        await redis.get("key")

    Usage (sync — Celery):
        redis = RedisManager.sync_client(db=2)
        redis.get("key")
    """

    _async_pools: ClassVar[dict[int, aioredis.ConnectionPool]] = {}
    _sync_pools: ClassVar[dict[int, redis.ConnectionPool]] = {}

    # ── Async (for FastAPI) ───────────────────────────────────────────────────

    @classmethod
    async def async_client(cls, db: int = REDIS_DB_DEFAULT) -> aioredis.Redis:
        """Return an async Redis client backed by a shared connection pool."""
        if db not in cls._async_pools:
            cls._async_pools[db] = aioredis.ConnectionPool.from_url(
                settings.REDIS_URL,
                db=db,
                max_connections=settings.REDIS_POOL_SIZE,
                socket_connect_timeout=2,
                socket_timeout=2,
                decode_responses=True,
            )
            logger.info("Created async Redis pool for db=%d (max=%d)", db, settings.REDIS_POOL_SIZE)
        return aioredis.Redis(connection_pool=cls._async_pools[db])

    # ── Sync (for Celery workers) ─────────────────────────────────────────────

    @classmethod
    def sync_client(cls, db: int = REDIS_DB_DEFAULT) -> redis.Redis:
        """Return a sync Redis client backed by a shared connection pool."""
        if db not in cls._sync_pools:
            cls._sync_pools[db] = redis.ConnectionPool.from_url(
                settings.REDIS_URL,
                db=db,
                max_connections=settings.REDIS_POOL_SIZE,
                socket_connect_timeout=2,
                socket_timeout=2,
                decode_responses=True,
            )
            logger.info("Created sync Redis pool for db=%d (max=%d)", db, settings.REDIS_POOL_SIZE)
        return redis.Redis(connection_pool=cls._sync_pools[db])

    # ── Cleanup ───────────────────────────────────────────────────────────────

    @classmethod
    async def close_async(cls) -> None:
        """Gracefully close all async pools (call in lifespan shutdown)."""
        for db, pool in cls._async_pools.items():
            await pool.disconnect()
            logger.info("Closed async Redis pool db=%d", db)
        cls._async_pools.clear()

    @classmethod
    def close_sync(cls) -> None:
        """Gracefully close all sync pools."""
        for db, pool in cls._sync_pools.items():
            pool.disconnect()
            logger.info("Closed sync Redis pool db=%d", db)
        cls._sync_pools.clear()


# ── Convenience shortcuts ─────────────────────────────────────────────────────

async def get_blacklist_redis() -> aioredis.Redis:
    """Async Redis for JWT blacklist (FastAPI)."""
    return await RedisManager.async_client(db=REDIS_DB_BLACKLIST)


async def get_weather_redis() -> aioredis.Redis:
    """Async Redis for weather cache flags (FastAPI)."""
    return await RedisManager.async_client(db=REDIS_DB_WEATHER)


async def get_cache_redis() -> aioredis.Redis:
    """Async Redis for general cache (FastAPI)."""
    return await RedisManager.async_client(db=REDIS_DB_CACHE)


def get_blacklist_redis_sync() -> redis.Redis:
    """Sync Redis for JWT blacklist (Celery)."""
    return RedisManager.sync_client(db=REDIS_DB_BLACKLIST)


def get_weather_redis_sync() -> redis.Redis:
    """Sync Redis for weather cache flags (Celery)."""
    return RedisManager.sync_client(db=REDIS_DB_WEATHER)

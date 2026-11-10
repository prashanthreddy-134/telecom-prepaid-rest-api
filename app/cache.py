
import hashlib
import json
import logging

import redis

from app.core import settings


logger = logging.getLogger(__name__)

PLAN_CACHE_GENERATION_KEY = "telecom:plans:cache-generation"

_redis_client = None


def get_redis():
    """Create the Redis client lazily."""
    global _redis_client

    if _redis_client is None:
        _redis_client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
        )

    return _redis_client


def get_plan_cache_generation() -> int | None:
    """Return the current cache generation, or None if Redis is unavailable."""
    try:
        value = get_redis().get(PLAN_CACHE_GENERATION_KEY)
        return int(value or 0)

    except (redis.RedisError, OSError, ValueError):
        logger.warning("Redis unavailable while reading plan cache generation")
        return None


def get_json(key: str) -> dict | None:
    """Read a JSON object from Redis."""
    try:
        value = get_redis().get(key)

        if value is None:
            return None

        result = json.loads(value)

        return result if isinstance(result, dict) else None

    except (redis.RedisError, OSError, ValueError, TypeError):
        logger.warning("Redis cache read failed")
        return None


def set_json(key: str, value: dict) -> bool:
    """Store a JSON object with the configured TTL."""
    try:
        get_redis().set(
            key,
            json.dumps(value),
            ex=settings.plan_cache_ttl_seconds,
        )
        return True

    except (redis.RedisError, OSError, TypeError, ValueError):
        logger.warning("Redis cache write failed")
        return False

def invalidate_plan_cache() -> bool:
    """
    Increment the generation after a successful plan mutation.

    Old entries become unreachable and expire naturally.
    """
    try:
        get_redis().incr(PLAN_CACHE_GENERATION_KEY)
        return True

    except (redis.RedisError, OSError):
        logger.warning("Could not invalidate plan cache")
        return False


def build_plan_list_cache_key(
    generation: int,
    q: str | None,
    max_price_paise: int | None,
    min_data_mb: int | None,
    page_num: int,
    size: int,
) -> str:
    """Build a unique cache key for every filter and pagination combination."""
    parameters = {
        "q": q,
        "max_price_paise": max_price_paise,
        "min_data_mb": min_data_mb,
        "page_num": page_num,
        "size": size,
    }

    serialized = json.dumps(
        parameters,
        sort_keys=True,
        separators=(",", ":"),
    )

    digest = hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()

    return f"telecom:plans:v1:g{generation}:list:{digest}"


def build_plan_detail_cache_key(
    generation: int,
    plan_id: int,
) -> str:
    return f"telecom:plans:v1:g{generation}:detail:{plan_id}"

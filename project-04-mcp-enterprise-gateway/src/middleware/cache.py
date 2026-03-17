"""
cache.py
~~~~~~~~
Redis-based tool response cache for MCP tools.
Decorator-based API: @cached(ttl=300) on any FastMCP tool function.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
from typing import Any, Callable

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_redis_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        import os
        _redis_client = aioredis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/1"),
            decode_responses=True,
        )
    return _redis_client


def _make_cache_key(func_name: str, kwargs: dict) -> str:
    """Create a deterministic cache key from function name and arguments."""
    args_hash = hashlib.sha256(
        json.dumps(kwargs, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    return f"mcp:tool:{func_name}:{args_hash}"


def cached(ttl: int = 300):
    """
    Decorator to cache MCP tool responses in Redis.

    Args:
        ttl: Cache TTL in seconds. 0 = no cache.

    Usage:
        @cached(ttl=300)
        @mcp.tool
        async def my_tool(arg1: str) -> dict: ...
    """
    def decorator(func: Callable) -> Callable:
        if ttl == 0:
            return func  # No caching

        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            redis = get_redis()

            # Build cache key (exclude FastMCP Context from key)
            cache_kwargs = {k: v for k, v in kwargs.items() if k != "ctx"}
            cache_key = _make_cache_key(func.__name__, cache_kwargs)

            # Try cache hit
            cached_value = await redis.get(cache_key)
            if cached_value is not None:
                logger.debug("Cache HIT: %s", cache_key)
                return json.loads(cached_value)

            logger.debug("Cache MISS: %s", cache_key)

            # Call the actual function
            result = await func(*args, **kwargs)

            # Store in cache
            try:
                await redis.setex(cache_key, ttl, json.dumps(result, default=str))
            except Exception as e:
                logger.warning("Cache write failed: %s", e)

            return result

        wrapper._cache_ttl = ttl
        return wrapper

    return decorator


async def invalidate_tool_cache(tool_name: str) -> int:
    """Invalidate all cache entries for a specific tool. Returns count deleted."""
    redis = get_redis()
    pattern = f"mcp:tool:{tool_name}:*"
    keys = await redis.keys(pattern)
    if keys:
        return await redis.delete(*keys)
    return 0


async def get_cache_stats() -> dict[str, Any]:
    """Return cache hit statistics."""
    redis = get_redis()
    info = await redis.info("stats")
    all_keys = await redis.keys("mcp:tool:*")

    # Group by tool name
    tool_counts: dict[str, int] = {}
    for key in all_keys:
        parts = key.split(":")
        if len(parts) >= 3:
            tool_name = parts[2]
            tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1

    return {
        "total_cached_entries": len(all_keys),
        "by_tool": tool_counts,
        "redis_hits": info.get("keyspace_hits", 0),
        "redis_misses": info.get("keyspace_misses", 0),
    }

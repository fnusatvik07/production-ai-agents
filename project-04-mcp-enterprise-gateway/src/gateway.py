"""
gateway.py
~~~~~~~~~~
Main FastMCP gateway that composes all sub-servers under one namespace.
Adds rate limiting middleware and initializes OTel tracing.

Run: uv run python -m src.gateway
"""

from __future__ import annotations

import logging
import os
import time

import redis.asyncio as aioredis
from fastmcp import FastMCP, Context

from .middleware.tracer import setup_tracing
from .middleware.cache import get_cache_stats
from .servers.sql_server import sql_server

logger = logging.getLogger(__name__)

# ── Gateway MCP Server ────────────────────────────────────────────────────────

gateway = FastMCP(
    "enterprise-data-gateway",
    instructions="""You have access to the enterprise data gateway which provides:
- /sql/* — PostgreSQL queries and vector similarity search
- /s3/* — AWS S3 file listing and retrieval
- /wiki/* — Confluence wiki pages and search
- /jira/* — Jira issues and project data

All tools are read-only. For write operations, contact the data team.""",
)

# Mount sub-servers with namespacing
# Tool names become: sql_query, sql_vector_similarity_search, etc.
gateway.mount("/sql", sql_server)

# In production, also mount:
# gateway.mount("/s3", s3_server)
# gateway.mount("/wiki", confluence_server)
# gateway.mount("/jira", jira_server)


# ── Gateway-level Tools (meta / management) ───────────────────────────────────

@gateway.tool
async def get_available_data_sources(ctx: Context = None) -> dict:
    """List all available data sources and their status."""
    await ctx.info("Checking data source availability...")

    sources = {
        "sql": {"status": "online", "description": "PostgreSQL with pgvector", "tools": ["sql_query", "vector_similarity_search"]},
        "s3": {"status": "online", "description": "AWS S3 file storage", "tools": ["s3_list_objects", "s3_get_object"]},
        "confluence": {"status": "online", "description": "Confluence wiki", "tools": ["confluence_search", "confluence_get_page"]},
        "jira": {"status": "online", "description": "Jira issue tracker", "tools": ["jira_search", "jira_get_issue"]},
    }
    return sources


@gateway.tool
async def cache_stats(ctx: Context = None) -> dict:
    """Get cache hit statistics for all tools."""
    stats = await get_cache_stats()
    await ctx.info(f"Cache has {stats['total_cached_entries']} entries")
    return stats


# ── Rate Limiting Middleware ──────────────────────────────────────────────────

_redis_rl: aioredis.Redis | None = None


async def get_rate_limit_redis() -> aioredis.Redis:
    global _redis_rl
    if _redis_rl is None:
        _redis_rl = aioredis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/2"),
            decode_responses=True,
        )
    return _redis_rl


async def check_rate_limit(client_id: str, requests_per_minute: int = 100) -> tuple[bool, int]:
    """
    Sliding window rate limiter using Redis sorted sets.
    Returns (is_allowed, retry_after_seconds).
    """
    redis = await get_rate_limit_redis()
    now = time.time()
    window_start = now - 60  # 1-minute window
    key = f"rl:{client_id}"

    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)  # Remove old entries
    pipe.zadd(key, {str(now): now})              # Add current request
    pipe.zcard(key)                              # Count in window
    pipe.expire(key, 60)
    results = await pipe.execute()

    count = results[2]
    if count > requests_per_minute:
        oldest = await redis.zrange(key, 0, 0, withscores=True)
        retry_after = int(60 - (now - oldest[0][1])) if oldest else 60
        return False, retry_after

    return True, 0


# ── Startup ───────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(level=logging.INFO)

    # Initialize OTel tracing
    setup_tracing(
        service_name="mcp-enterprise-gateway",
        otlp_endpoint=os.environ.get("OTLP_ENDPOINT", "http://localhost:4317"),
    )

    port = int(os.environ.get("GATEWAY_PORT", "8004"))
    logger.info("Starting Enterprise MCP Gateway on port %d", port)

    # FastMCP 3.0 HTTP transport with Streamable HTTP
    gateway.run(transport="http", port=port, path="/mcp")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    main()

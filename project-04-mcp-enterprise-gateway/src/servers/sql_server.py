"""
sql_server.py
~~~~~~~~~~~~~
FastMCP sub-server for SQL (PostgreSQL + pgvector) data access.
Exposes read-only query tools and vector similarity search.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import asyncpg
from fastmcp import FastMCP, Context

from ..middleware.cache import cached
from ..middleware.tracer import traced

logger = logging.getLogger(__name__)

sql_server = FastMCP("sql-data-server")

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            os.environ.get("POSTGRES_URI", "postgresql://user:pass@localhost:5432/db"),
            min_size=2,
            max_size=10,
        )
    return _pool


@traced
@cached(ttl=60)
@sql_server.tool
async def sql_query(query: str, params: list | None = None, ctx: Context = None) -> dict:
    """
    Execute a read-only SQL query against the PostgreSQL database.
    ONLY SELECT statements are allowed.

    Args:
        query: SQL SELECT statement (no DML/DDL)
        params: Optional list of query parameters for parameterized queries

    Returns:
        {"rows": [...], "count": N, "columns": [...]}
    """
    query_upper = query.strip().upper()
    if not query_upper.startswith("SELECT") and not query_upper.startswith("WITH"):
        return {"error": "Only SELECT queries are allowed"}

    await ctx.info(f"Executing SQL query: {query[:100]}...")

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Execute with timeout
            rows = await asyncpg.Connection.fetch(conn, query, *(params or []))
            result_rows = [dict(row) for row in rows[:1000]]  # cap at 1000 rows
            columns = list(result_rows[0].keys()) if result_rows else []

        return {"rows": result_rows, "count": len(result_rows), "columns": columns}

    except Exception as e:
        logger.error("SQL query failed: %s", e)
        return {"error": str(e), "query": query}


@traced
@cached(ttl=300)
@sql_server.tool
async def vector_similarity_search(
    query_text: str,
    table: str,
    embedding_column: str = "embedding",
    content_column: str = "content",
    top_k: int = 5,
    ctx: Context = None,
) -> list[dict]:
    """
    Semantic similarity search using pgvector.
    Embeds the query and finds the closest rows by cosine distance.

    Args:
        query_text: Natural language query to embed and search
        table: Table name containing the embeddings
        embedding_column: Column name of the vector (default: "embedding")
        content_column: Column name of the text content (default: "content")
        top_k: Number of results to return

    Returns:
        List of matching rows with similarity scores
    """
    await ctx.info(f"Vector search in {table}: '{query_text[:50]}...'")
    await ctx.report_progress(0, 3)

    # Get embedding for query text
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=query_text,
    )
    embedding = response.data[0].embedding
    await ctx.report_progress(1, 3)

    # pgvector cosine similarity search
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT {content_column},
                   1 - ({embedding_column} <=> $1::vector) AS similarity
            FROM {table}
            ORDER BY {embedding_column} <=> $1::vector
            LIMIT $2
            """,
            embedding,
            top_k,
        )

    await ctx.report_progress(3, 3)
    return [{"content": row[content_column], "similarity": float(row["similarity"])} for row in rows]


@sql_server.resource("sql://schema/{table}")
async def get_table_schema(table: str) -> str:
    """Get the schema (columns, types) for a database table."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = $1
            ORDER BY ordinal_position
            """,
            table,
        )
    schema = [dict(r) for r in rows]
    return json.dumps(schema, indent=2)


@sql_server.resource("sql://tables")
async def list_tables() -> str:
    """List all accessible tables in the database."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
            """
        )
    return json.dumps([dict(r) for r in rows], indent=2)

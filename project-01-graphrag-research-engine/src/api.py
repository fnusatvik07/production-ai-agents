"""
api.py
~~~~~~
FastAPI server exposing the GraphRAG research agent.
Endpoints:
  POST /research         — blocking, returns full answer
  POST /research/stream  — SSE streaming of LangGraph events
  GET  /health           — health check
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from langchain_openai import OpenAIEmbeddings
from neo4j import AsyncGraphDatabase
from pydantic import BaseModel
import chromadb

from .agent import build_graph
from .config import settings
from .retrieval import DRIFTRetriever, HybridRetriever

logger = logging.getLogger(__name__)

# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize all resources on startup, clean up on shutdown."""
    logger.info("Starting GraphRAG Research Engine...")

    # Shared clients
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    neo4j_driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
    )
    chroma_client = chromadb.HttpClient(
        host=settings.chroma_host, port=settings.chroma_port
    )
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=settings.openai_api_key,
    )

    # Collections
    doc_collection = chroma_client.get_or_create_collection("documents")
    community_collection = chroma_client.get_or_create_collection("community_summaries")

    # Retrievers — in production, pass real document list for BM25
    # Here we initialize with an empty corpus; run ingest first
    hybrid_retriever = HybridRetriever(
        documents=[],  # populated after ingestion
        embeddings=embeddings,
        chroma_collection=doc_collection,
        redis_client=redis_client,
    )
    drift_retriever = DRIFTRetriever(
        neo4j_driver=neo4j_driver,
        community_collection=community_collection,
        embeddings=embeddings,
        redis_client=redis_client,
        max_hops=settings.drift_max_hops,
    )

    # Build LangGraph
    graph = build_graph(hybrid_retriever, drift_retriever)

    # Attach to app state
    app.state.graph = graph
    app.state.redis = redis_client
    app.state.neo4j = neo4j_driver

    logger.info("GraphRAG Research Engine ready.")
    yield

    # Shutdown
    await redis_client.aclose()
    await neo4j_driver.close()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="GraphRAG Research Engine",
    description="Adaptive knowledge-graph RAG with DRIFT search and CRAG",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Request / Response Models ─────────────────────────────────────────────────

class ResearchRequest(BaseModel):
    query: str
    thread_id: str | None = None


class ResearchResponse(BaseModel):
    answer: str
    sources: list[str]
    query_type: str
    rewrite_count: int
    relevance_score: float
    thread_id: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/research", response_model=ResearchResponse)
async def research(request: ResearchRequest):
    """Blocking research endpoint. Returns full answer when complete."""
    thread_id = request.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    try:
        result = await app.state.graph.ainvoke(
            {
                "messages": [("human", request.query)],
                "query": request.query,
                "rewrite_count": 0,
                "relevance_score": 0.0,
            },
            config=config,
        )
    except Exception as e:
        logger.exception("Research failed for query: %s", request.query)
        raise HTTPException(status_code=500, detail=str(e))

    return ResearchResponse(
        answer=result.get("answer", ""),
        sources=result.get("sources", []),
        query_type=result.get("query_type", "unknown"),
        rewrite_count=result.get("rewrite_count", 0),
        relevance_score=result.get("relevance_score", 0.0),
        thread_id=thread_id,
    )


@app.post("/research/stream")
async def research_stream(request: ResearchRequest):
    """SSE streaming endpoint — emits LangGraph node events as they happen."""
    thread_id = request.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    async def generate() -> AsyncGenerator[str, None]:
        try:
            async for event in app.state.graph.astream_events(
                {
                    "messages": [("human", request.query)],
                    "query": request.query,
                    "rewrite_count": 0,
                    "relevance_score": 0.0,
                },
                config=config,
                version="v2",
            ):
                event_type = event.get("event", "")
                node_name = event.get("name", "")

                # Stream node completion events with partial state
                if event_type == "on_chain_end" and node_name in {
                    "classify_query",
                    "evaluate_relevance",
                    "rewrite_query",
                    "generate_answer",
                }:
                    payload = {
                        "node": node_name,
                        "data": event.get("data", {}).get("output", {}),
                    }
                    yield f"data: {json.dumps(payload)}\n\n"

                # Stream LLM tokens
                elif event_type == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        yield f"data: {json.dumps({'token': chunk.content})}\n\n"

            yield f"data: {json.dumps({'done': True, 'thread_id': thread_id})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Thread-ID": thread_id},
    )


def cli_serve() -> None:
    import uvicorn
    uvicorn.run(
        "src.api:app",
        host=settings.api_host,
        port=settings.api_port,
        workers=settings.api_workers,
        reload=True,
    )

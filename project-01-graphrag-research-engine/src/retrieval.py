"""
retrieval.py
~~~~~~~~~~~~
Hybrid retrieval (BM25 + dense vectors) fused with Reciprocal Rank Fusion,
plus DRIFT-style graph traversal for synthesis questions.
Includes Redis-backed embedding cache and semantic result cache.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

import redis.asyncio as aioredis
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from neo4j import AsyncGraphDatabase
from rank_bm25 import BM25Okapi
import chromadb

from .config import settings

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    text: str
    score: float
    source: str
    metadata: dict[str, Any]


# ── Reciprocal Rank Fusion ─────────────────────────────────────────────────────

def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievedChunk]],
    k: int = 60,
) -> list[RetrievedChunk]:
    """
    Merge multiple ranked lists using RRF.
    k=60 is the standard constant from the original RRF paper.
    """
    scores: dict[str, float] = {}
    chunks_map: dict[str, RetrievedChunk] = {}

    for ranked_list in ranked_lists:
        for rank, chunk in enumerate(ranked_list, start=1):
            key = hashlib.md5(chunk.text.encode()).hexdigest()
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            chunks_map[key] = chunk

    sorted_keys = sorted(scores, key=lambda k: scores[k], reverse=True)
    return [chunks_map[k] for k in sorted_keys]


# ── Hybrid Retriever ──────────────────────────────────────────────────────────

class HybridRetriever:
    """BM25 + dense vector search fused with RRF."""

    def __init__(
        self,
        documents: list[Document],
        embeddings: OpenAIEmbeddings,
        chroma_collection: chromadb.Collection,
        redis_client: aioredis.Redis,
    ) -> None:
        self._embeddings = embeddings
        self._chroma = chroma_collection
        self._redis = redis_client

        # Build BM25 corpus
        self._corpus = [doc.page_content for doc in documents]
        tokenized = [doc.page_content.lower().split() for doc in documents]
        self._bm25 = BM25Okapi(tokenized)
        self._docs = documents

    async def _get_query_embedding(self, query: str) -> list[float]:
        """Embed query with Redis cache (TTL = EMBEDDING_CACHE_TTL_SECONDS)."""
        cache_key = f"embed:{hashlib.sha256(query.encode()).hexdigest()}"
        cached = await self._redis.get(cache_key)
        if cached:
            return json.loads(cached)

        embedding = await self._embeddings.aembed_query(query)
        await self._redis.setex(
            cache_key,
            settings.embedding_cache_ttl_seconds,
            json.dumps(embedding),
        )
        return embedding

    async def _bm25_search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        tokenized_query = query.lower().split()
        scores = self._bm25.get_scores(tokenized_query)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [
            RetrievedChunk(
                text=self._corpus[i],
                score=float(scores[i]),
                source="bm25",
                metadata=self._docs[i].metadata,
            )
            for i in top_indices
        ]

    async def _dense_search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        embedding = await self._get_query_embedding(query)
        results = self._chroma.query(
            query_embeddings=[embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        chunks = []
        for text, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            chunks.append(RetrievedChunk(
                text=text,
                score=1.0 - dist,  # cosine distance → similarity
                source="dense",
                metadata=meta or {},
            ))
        return chunks

    async def search(self, query: str, top_k: int = 20) -> list[RetrievedChunk]:
        """Run BM25 and dense search in parallel, fuse with RRF."""
        bm25_results, dense_results = await asyncio.gather(
            self._bm25_search(query, top_k),
            self._dense_search(query, top_k),
        )
        fused = reciprocal_rank_fusion([bm25_results, dense_results])
        return fused[:top_k]


# ── DRIFT Graph Traversal ─────────────────────────────────────────────────────

class DRIFTRetriever:
    """
    DRIFT-style retrieval:
    1. Use HyDE (Hypothetical Document Embedding) to query community summaries
    2. Identify relevant communities
    3. Traverse from community entities to find specific facts (graph traversal)
    4. Run parallel follow-up searches within identified sub-graphs
    """

    def __init__(
        self,
        neo4j_driver: AsyncGraphDatabase,
        community_collection: chromadb.Collection,
        embeddings: OpenAIEmbeddings,
        redis_client: aioredis.Redis,
        max_hops: int = 3,
    ) -> None:
        self._driver = neo4j_driver
        self._community_col = community_collection
        self._embeddings = embeddings
        self._redis = redis_client
        self._max_hops = max_hops

    async def _hyde_embed(self, query: str, llm: Any) -> list[float]:
        """Generate a hypothetical answer and embed it (HyDE technique)."""
        from langchain_core.prompts import ChatPromptTemplate
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Write a 2-sentence answer to the following research question. Be specific and factual."),
            ("human", "{query}"),
        ])
        chain = prompt | llm
        response = await chain.ainvoke({"query": query})
        hypothetical_answer = response.content

        cache_key = f"hyde:{hashlib.sha256(hypothetical_answer.encode()).hexdigest()}"
        cached = await self._redis.get(cache_key)
        if cached:
            return json.loads(cached)

        embedding = await self._embeddings.aembed_query(hypothetical_answer)
        await self._redis.setex(
            cache_key,
            settings.embedding_cache_ttl_seconds,
            json.dumps(embedding),
        )
        return embedding

    async def _get_community_entities(self, community_id: int) -> list[dict]:
        """Fetch all entities in a community from Neo4j."""
        async with self._driver.session() as session:
            result = await session.run(
                "MATCH (e:Entity {communityId: $cid}) RETURN e.id AS id, e.name AS name, e.description AS description",
                {"cid": community_id},
            )
            return [dict(record) async for record in result]

    async def _traverse_from_entities(
        self, entity_ids: list[str], max_hops: int
    ) -> list[dict]:
        """BFS traversal from seed entities up to max_hops deep."""
        async with self._driver.session() as session:
            result = await session.run(
                f"""
                MATCH path = (start:Entity)-[*1..{max_hops}]-(connected:Entity)
                WHERE start.id IN $ids
                RETURN DISTINCT connected.id AS id,
                               connected.name AS name,
                               connected.description AS description,
                               length(path) AS distance
                ORDER BY distance
                LIMIT 50
                """,
                {"ids": entity_ids},
            )
            return [dict(record) async for record in result]

    async def retrieve(
        self,
        query: str,
        llm: Any,
        community_top_k: int = 3,
    ) -> list[RetrievedChunk]:
        """Full DRIFT retrieval pipeline."""
        # 1. HyDE embedding for community search
        hyde_embedding = await self._hyde_embed(query, llm)

        # 2. Find top-k relevant communities
        community_results = self._community_col.query(
            query_embeddings=[hyde_embedding],
            n_results=community_top_k,
            include=["documents", "metadatas"],
        )

        chunks: list[RetrievedChunk] = []

        # 3. For each community, traverse the graph in parallel
        async def process_community(summary: str, meta: dict) -> list[RetrievedChunk]:
            community_id = meta.get("community_id")
            # Add community summary itself
            local_chunks = [RetrievedChunk(
                text=summary,
                score=0.9,
                source="community_summary",
                metadata=meta,
            )]

            if community_id is not None:
                entities = await self._get_community_entities(community_id)
                entity_ids = [e["id"] for e in entities[:10]]
                traversed = await self._traverse_from_entities(entity_ids, self._max_hops)

                for entity in traversed:
                    if entity.get("description"):
                        local_chunks.append(RetrievedChunk(
                            text=f"{entity['name']}: {entity['description']}",
                            score=max(0.1, 0.9 - entity["distance"] * 0.15),
                            source=f"graph_traversal:hop_{entity['distance']}",
                            metadata={"entity_id": entity["id"]},
                        ))
            return local_chunks

        tasks = [
            process_community(doc, meta)
            for doc, meta in zip(
                community_results["documents"][0],
                community_results["metadatas"][0],
            )
        ]
        results = await asyncio.gather(*tasks)
        for result in results:
            chunks.extend(result)

        # Sort by score descending
        chunks.sort(key=lambda c: c.score, reverse=True)
        return chunks[:settings.hybrid_search_top_k]

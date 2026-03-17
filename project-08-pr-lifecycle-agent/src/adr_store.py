"""
adr_store.py
~~~~~~~~~~~~
ADR (Architecture Decision Record) ingestion and semantic retrieval.
Builds a Chroma knowledge base from Markdown ADR files.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import chromadb
from langchain_openai import OpenAIEmbeddings

logger = logging.getLogger(__name__)


class ADRStore:
    def __init__(
        self,
        chroma_host: str = "localhost",
        chroma_port: int = 8000,
        openai_api_key: str = "",
    ) -> None:
        self._client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
        self._embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=openai_api_key,
        )
        self._collection = self._client.get_or_create_collection(
            "adrs",
            metadata={"hnsw:space": "cosine"},
        )

    def _parse_adr(self, path: Path) -> dict[str, str]:
        """Parse an ADR Markdown file into structured fields."""
        content = path.read_text()
        adr_id_match = re.search(r"ADR[-_]?(\d+)", path.stem, re.IGNORECASE)
        adr_id = f"ADR-{adr_id_match.group(1)}" if adr_id_match else path.stem

        # Extract title from first H1
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        title = title_match.group(1) if title_match else path.stem

        # Extract status
        status_match = re.search(r"##\s+Status[:\s]+(\w+)", content, re.IGNORECASE)
        status = status_match.group(1) if status_match else "Unknown"

        # Extract decision section
        decision_match = re.search(
            r"##\s+Decision\s*\n(.*?)(?=##|\Z)", content, re.DOTALL | re.IGNORECASE
        )
        decision = decision_match.group(1).strip() if decision_match else content

        return {
            "adr_id": adr_id,
            "title": title,
            "status": status,
            "content": content,
            "decision": decision,
            "path": str(path),
        }

    async def ingest_directory(self, directory: Path) -> int:
        """Ingest all Markdown ADR files from a directory."""
        adr_files = list(directory.glob("*.md")) + list(directory.glob("**/*.md"))
        ingested = 0

        for path in adr_files:
            adr = self._parse_adr(path)
            if adr["status"].lower() in ("accepted", "superseded", "deprecated"):
                # Only index decision-relevant statuses
                embedding = await self._embeddings.aembed_query(
                    f"{adr['title']}\n{adr['decision']}"
                )
                self._collection.upsert(
                    ids=[adr["adr_id"]],
                    embeddings=[embedding],
                    documents=[f"{adr['title']}\n\n{adr['decision']}"],
                    metadatas=[{k: v for k, v in adr.items() if k != "content"}],
                )
                ingested += 1
                logger.info("Indexed ADR: %s — %s (%s)", adr["adr_id"], adr["title"], adr["status"])

        logger.info("Ingested %d ADRs from %s", ingested, directory)
        return ingested

    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Semantic search over ADRs."""
        embedding = await self._embeddings.aembed_query(query)
        results = self._collection.query(
            query_embeddings=[embedding],
            n_results=min(top_k, self._collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        adrs = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            adrs.append({
                "adr_id": meta.get("adr_id", ""),
                "title": meta.get("title", ""),
                "status": meta.get("status", ""),
                "content": doc,
                "path": meta.get("path", ""),
                "relevance": round(1.0 - dist, 3),
            })

        return adrs

"""
runbook_store.py
~~~~~~~~~~~~~~~~
Chroma-backed runbook knowledge base with semantic retrieval.
"""

from __future__ import annotations

import logging
from pathlib import Path

import chromadb
from langchain_community.document_loaders import TextLoader
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import settings

logger = logging.getLogger(__name__)


class RunbookStore:
    def __init__(self) -> None:
        self._client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
        )
        self._embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=settings.openai_api_key,
        )
        self._collection = self._client.get_or_create_collection(
            "runbooks",
            metadata={"hnsw:space": "cosine"},
        )

    async def ingest(self, path: Path) -> None:
        """Ingest a runbook Markdown file into Chroma."""
        loader = TextLoader(str(path))
        docs = loader.load()

        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        chunks = splitter.split_documents(docs)

        texts = [c.page_content for c in chunks]
        embeddings = await self._embeddings.aembed_documents(texts)
        ids = [f"{path.stem}_{i}" for i in range(len(chunks))]
        metadatas = [{"source": str(path), "chunk": i} for i in range(len(chunks))]

        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        logger.info("Ingested %d chunks from %s", len(chunks), path.name)

    async def retrieve(self, query: str, top_k: int = 5) -> str:
        """Retrieve and concatenate the most relevant runbook chunks."""
        embedding = await self._embeddings.aembed_query(query)
        results = self._collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            include=["documents", "metadatas"],
        )

        if not results["documents"][0]:
            return "No relevant runbook found. Follow general SRE best practices."

        # Group by source runbook
        sources: dict[str, list[str]] = {}
        for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
            source = meta.get("source", "unknown")
            sources.setdefault(source, []).append(doc)

        # Return the runbook with most matching chunks
        best_source = max(sources, key=lambda s: len(sources[s]))
        return "\n\n".join(sources[best_source])


def cli_ingest() -> None:
    """Entry point: uv run python -m src.runbook_store --ingest runbooks/"""
    import argparse
    import asyncio
    import glob as glob_module

    parser = argparse.ArgumentParser()
    parser.add_argument("--ingest", required=True, help="Directory or glob of runbook files")
    args = parser.parse_args()

    paths = [Path(p) for p in glob_module.glob(args.ingest + "/**/*.md", recursive=True)]
    if not paths:
        paths = [Path(p) for p in glob_module.glob(args.ingest + "/*.md")]

    store = RunbookStore()

    async def run():
        for path in paths:
            await store.ingest(path)

    asyncio.run(run())
    print(f"Ingested {len(paths)} runbooks.")

"""
graph_builder.py
~~~~~~~~~~~~~~~~
Ingests documents (PDF, arxiv, web) into a Neo4j knowledge graph.

Pipeline:
  Document → chunk → embed → extract entities/relationships (LLM) → Neo4j
  Community detection (GDS Leiden) → community summaries → Chroma
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import httpx
from langchain_anthropic import ChatAnthropic
from langchain_community.document_loaders import PyPDFLoader, WebBaseLoader
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import OpenAIEmbeddings
from neo4j import AsyncGraphDatabase
import chromadb

from .config import settings

logger = logging.getLogger(__name__)


# ── Entity / Relationship Extraction ──────────────────────────────────────────

EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a knowledge graph extractor. Given a text chunk, extract:
1. Named entities (methods, datasets, authors, concepts, frameworks)
2. Relationships between them

Return ONLY valid JSON in this exact format:
{
  "entities": [
    {"id": "unique_snake_case_id", "label": "EntityType", "name": "Display Name", "description": "brief description"}
  ],
  "relationships": [
    {"from": "entity_id_1", "to": "entity_id_2", "type": "RELATIONSHIP_TYPE", "properties": {}}
  ]
}

Entity types: Method, Dataset, Author, Framework, Concept, Tool, Paper
Relationship types: USES, EXTENDS, EVALUATES_ON, PROPOSES, COMPARES_WITH, IMPLEMENTS, CITES"""),
    ("human", "Text chunk:\n\n{text}"),
])


async def extract_graph_elements(
    text: str,
    llm: ChatAnthropic,
) -> dict[str, list[dict]]:
    """Use Claude to extract entities and relationships from a text chunk."""
    chain = EXTRACTION_PROMPT | llm
    response = await chain.ainvoke({"text": text[:4000]})  # stay within context

    try:
        # Parse JSON from response
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        return json.loads(content.strip())
    except (json.JSONDecodeError, IndexError) as e:
        logger.warning("Failed to parse graph elements: %s", e)
        return {"entities": [], "relationships": []}


# ── Neo4j Ingestion ───────────────────────────────────────────────────────────

class GraphBuilder:
    def __init__(self) -> None:
        self.driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
        )
        self.llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            temperature=0,
        )
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=settings.openai_api_key,
        )
        self.chroma = chromadb.HttpClient(
            host=settings.chroma_host, port=settings.chroma_port
        )
        self.community_collection = self.chroma.get_or_create_collection(
            "community_summaries",
            metadata={"hnsw:space": "cosine"},
        )

    async def close(self) -> None:
        await self.driver.close()

    async def ensure_schema(self) -> None:
        """Create Neo4j constraints and indexes."""
        queries = [
            "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
            "CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)",
            "CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS FOR (e:Entity) ON EACH [e.name, e.description]",
        ]
        async with self.driver.session() as session:
            for q in queries:
                await session.run(q)
        logger.info("Neo4j schema ready")

    async def upsert_entity(self, entity: dict[str, Any], source_doc_id: str) -> None:
        query = """
        MERGE (e:Entity {id: $id})
        SET e.label = $label,
            e.name = $name,
            e.description = $description,
            e.source_doc = $source_doc,
            e.updated_at = timestamp()
        """
        async with self.driver.session() as session:
            await session.run(query, {**entity, "source_doc": source_doc_id})

    async def upsert_relationship(self, rel: dict[str, Any]) -> None:
        query = f"""
        MATCH (a:Entity {{id: $from}})
        MATCH (b:Entity {{id: $to}})
        MERGE (a)-[r:{rel['type']}]->(b)
        SET r.properties = $properties, r.updated_at = timestamp()
        """
        async with self.driver.session() as session:
            await session.run(query, {
                "from": rel["from"],
                "to": rel["to"],
                "properties": json.dumps(rel.get("properties", {})),
            })

    async def ingest_document(self, doc: Document, source_id: str) -> None:
        """Chunk a document, extract graph elements, and persist to Neo4j."""
        # Simple chunking — in production use RecursiveCharacterTextSplitter
        text = doc.page_content
        chunks = [text[i:i+2000] for i in range(0, len(text), 1800)]  # 200 char overlap

        for chunk in chunks:
            elements = await extract_graph_elements(chunk, self.llm)
            for entity in elements.get("entities", []):
                await self.upsert_entity(entity, source_id)
            for rel in elements.get("relationships", []):
                await self.upsert_relationship(rel)

        logger.info("Ingested %d chunks from document %s", len(chunks), source_id)

    async def run_community_detection(self) -> list[dict]:
        """Run Leiden community detection via GDS and return community assignments."""
        async with self.driver.session() as session:
            # Project the graph for GDS
            await session.run("""
            CALL gds.graph.project.cypher(
              'entity-graph',
              'MATCH (e:Entity) RETURN id(e) AS id',
              'MATCH (a:Entity)-[r]->(b:Entity) RETURN id(a) AS source, id(b) AS target'
            )
            """)

            result = await session.run("""
            CALL gds.leiden.write('entity-graph', {
              writeProperty: 'communityId',
              maxLevels: 3
            })
            YIELD communityCount, modularity
            RETURN communityCount, modularity
            """)
            record = await result.single()
            logger.info(
                "Detected %d communities (modularity=%.3f)",
                record["communityCount"],
                record["modularity"],
            )

            # Fetch community members
            members_result = await session.run("""
            MATCH (e:Entity)
            RETURN e.communityId AS community_id,
                   collect(e.name + ': ' + coalesce(e.description, '')) AS members
            ORDER BY community_id
            """)
            communities = []
            async for record in members_result:
                communities.append({
                    "id": record["community_id"],
                    "members": record["members"],
                })

            # Drop the projected graph
            await session.run("CALL gds.graph.drop('entity-graph', false)")

        return communities

    async def generate_community_summaries(self, communities: list[dict]) -> None:
        """Generate LLM summaries for each community and index them in Chroma."""
        SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
            ("system", "Summarize the following group of related entities from a research knowledge graph. Write 2-3 sentences describing their domain and relationships."),
            ("human", "Entities:\n{members}"),
        ])
        chain = SUMMARY_PROMPT | self.llm

        ids, documents, metadatas = [], [], []
        for community in communities:
            members_text = "\n".join(community["members"][:30])  # cap at 30 members
            response = await chain.ainvoke({"members": members_text})
            summary = response.content

            comm_id = f"community_{community['id']}"
            embedding = await self.embeddings.aembed_query(summary)

            ids.append(comm_id)
            documents.append(summary)
            metadatas.append({"community_id": community["id"], "member_count": len(community["members"])})

        if ids:
            self.community_collection.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
            )
        logger.info("Indexed %d community summaries in Chroma", len(ids))

    async def build_from_paths(self, paths: list[Path]) -> None:
        """Full ingestion pipeline: load → extract → community detect → summarize."""
        await self.ensure_schema()

        for path in paths:
            doc_id = hashlib.sha256(str(path).encode()).hexdigest()[:16]
            if path.suffix.lower() == ".pdf":
                loader = PyPDFLoader(str(path))
                docs = loader.load()
            else:
                loader = WebBaseLoader(str(path))
                docs = loader.load()

            for doc in docs:
                await self.ingest_document(doc, doc_id)

        logger.info("All documents ingested. Running community detection...")
        communities = await self.run_community_detection()
        await self.generate_community_summaries(communities)
        logger.info("Graph build complete. %d communities indexed.", len(communities))


# ── CLI ───────────────────────────────────────────────────────────────────────

def cli_ingest() -> None:
    """Entry point: uv run python -m src.graph_builder --ingest <glob>"""
    import argparse
    import asyncio
    import glob as glob_module

    parser = argparse.ArgumentParser(description="Ingest documents into GraphRAG")
    parser.add_argument("--ingest", required=True, help="Glob pattern of files to ingest")
    args = parser.parse_args()

    paths = [Path(p) for p in glob_module.glob(args.ingest)]
    if not paths:
        print(f"No files matched: {args.ingest}")
        return

    print(f"Ingesting {len(paths)} files...")
    builder = GraphBuilder()

    async def run() -> None:
        try:
            await builder.build_from_paths(paths)
        finally:
            await builder.close()

    asyncio.run(run())
    print("Done.")

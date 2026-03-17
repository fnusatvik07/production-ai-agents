"""
agent.py
~~~~~~~~
LangGraph StateGraph implementing Corrective RAG (CRAG) with DRIFT fallback.

Flow:
  classify_query
      ├─► (simple) hybrid_retrieve → evaluate_relevance → [rewrite | generate]
      └─► (synthesis) drift_retrieve → generate
                                           ↑
                              rewrite_query ┘  (on low relevance)
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel
from typing_extensions import TypedDict

from .config import settings
from .retrieval import RetrievedChunk

logger = logging.getLogger(__name__)

# ── State ──────────────────────────────────────────────────────────────────────

class ResearchState(TypedDict):
    messages: Annotated[list, add_messages]
    query: str
    query_type: Literal["simple", "synthesis"]
    retrieved_chunks: list[RetrievedChunk]
    rewrite_count: int
    relevance_score: float
    answer: str
    sources: list[str]


# ── LLM ───────────────────────────────────────────────────────────────────────

def get_llm() -> ChatAnthropic:
    return ChatAnthropic(
        model="claude-sonnet-4-6",
        api_key=settings.anthropic_api_key,
        temperature=0,
        max_tokens=4096,
    )


# ── Nodes ─────────────────────────────────────────────────────────────────────

async def classify_query(state: ResearchState) -> dict:
    """Classify whether the query needs simple retrieval or synthesis across the graph."""
    llm = get_llm()

    class QueryClassification(BaseModel):
        query_type: Literal["simple", "synthesis"]
        reasoning: str

    structured_llm = llm.with_structured_output(QueryClassification)

    prompt = ChatPromptTemplate.from_messages([
        ("system", """Classify the research query as:
- "simple": asks for a specific fact, definition, or localized information
- "synthesis": asks for broad analysis, comparisons, trends, or requires aggregating across many sources

Reply with the query_type and brief reasoning."""),
        ("human", "{query}"),
    ])

    result = await (prompt | structured_llm).ainvoke({"query": state["query"]})
    logger.info("Query classified as: %s", result.query_type)
    return {"query_type": result.query_type}


async def hybrid_retrieve(state: ResearchState, retriever) -> dict:
    """Run hybrid BM25 + dense search with RRF fusion."""
    chunks = await retriever.search(state["query"], top_k=settings.hybrid_search_top_k)
    return {"retrieved_chunks": chunks}


async def drift_retrieve(state: ResearchState, drift_retriever, llm) -> dict:
    """Run DRIFT graph traversal for synthesis questions."""
    chunks = await drift_retriever.retrieve(
        state["query"],
        llm=llm,
        community_top_k=settings.drift_community_top_k,
    )
    return {"retrieved_chunks": chunks}


async def evaluate_relevance(state: ResearchState) -> dict:
    """Score how relevant the retrieved chunks are to the query."""
    llm = get_llm()

    class RelevanceScore(BaseModel):
        score: float
        reasoning: str

    structured_llm = llm.with_structured_output(RelevanceScore)

    context = "\n\n".join(c.text[:500] for c in state["retrieved_chunks"][:5])
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Score how relevant this context is for answering the query. Score 0.0 (irrelevant) to 1.0 (perfectly relevant)."),
        ("human", "Query: {query}\n\nContext:\n{context}"),
    ])

    result = await (prompt | structured_llm).ainvoke({
        "query": state["query"],
        "context": context,
    })
    logger.info("Relevance score: %.2f — %s", result.score, result.reasoning)
    return {"relevance_score": result.score}


async def rewrite_query(state: ResearchState) -> dict:
    """Rewrite the query to improve retrieval when relevance is low."""
    llm = get_llm()
    prompt = ChatPromptTemplate.from_messages([
        ("system", "The current search query didn't retrieve useful results. Rewrite it to be more specific and likely to match academic/technical documents. Return ONLY the rewritten query, nothing else."),
        ("human", "Original query: {query}"),
    ])
    result = await (prompt | llm).ainvoke({"query": state["query"]})
    new_query = result.content.strip()
    logger.info("Rewrote query: '%s' → '%s'", state["query"], new_query)
    return {
        "query": new_query,
        "rewrite_count": state.get("rewrite_count", 0) + 1,
    }


async def generate_answer(state: ResearchState) -> dict:
    """Generate a grounded answer from retrieved context."""
    llm = get_llm()

    context = "\n\n---\n\n".join(
        f"[Source: {c.source}]\n{c.text}"
        for c in state["retrieved_chunks"][:settings.reranker_top_k]
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a research assistant. Answer the query using ONLY the provided context.
- Cite sources inline as [Source: ...]
- If the context doesn't contain enough information, say so explicitly
- Be precise and academic in tone
- Structure the answer with bullet points or numbered lists for complex answers"""),
        ("human", "Query: {query}\n\nContext:\n{context}"),
    ])

    response = await (prompt | llm).ainvoke({
        "query": state["query"],
        "context": context,
    })

    sources = list({c.source for c in state["retrieved_chunks"][:settings.reranker_top_k]})
    return {
        "answer": response.content,
        "sources": sources,
        "messages": [AIMessage(content=response.content)],
    }


# ── Routing Functions ──────────────────────────────────────────────────────────

def route_by_query_type(state: ResearchState) -> Literal["hybrid_retrieve", "drift_retrieve"]:
    if state["query_type"] == "synthesis":
        return "drift_retrieve"
    return "hybrid_retrieve"


def route_by_relevance(state: ResearchState) -> Literal["generate_answer", "rewrite_query"]:
    # If relevance is high enough OR we've already rewritten twice, generate
    if state["relevance_score"] >= 0.6 or state.get("rewrite_count", 0) >= 2:
        return "generate_answer"
    return "rewrite_query"


# ── Graph Builder ──────────────────────────────────────────────────────────────

def build_graph(hybrid_retriever, drift_retriever) -> Any:
    """Construct and compile the LangGraph StateGraph."""
    llm = get_llm()

    # Wrap nodes that need injected dependencies
    async def _hybrid_retrieve(state: ResearchState) -> dict:
        return await hybrid_retrieve(state, hybrid_retriever)

    async def _drift_retrieve(state: ResearchState) -> dict:
        return await drift_retrieve(state, drift_retriever, llm)

    builder = StateGraph(ResearchState)

    # Add all nodes
    builder.add_node("classify_query", classify_query)
    builder.add_node("hybrid_retrieve", _hybrid_retrieve)
    builder.add_node("drift_retrieve", _drift_retrieve)
    builder.add_node("evaluate_relevance", evaluate_relevance)
    builder.add_node("rewrite_query", rewrite_query)
    builder.add_node("generate_answer", generate_answer)

    # Wire edges
    builder.add_edge(START, "classify_query")

    builder.add_conditional_edges(
        "classify_query",
        route_by_query_type,
        {"hybrid_retrieve": "hybrid_retrieve", "drift_retrieve": "drift_retrieve"},
    )

    # After hybrid retrieval → evaluate relevance
    builder.add_edge("hybrid_retrieve", "evaluate_relevance")

    # After relevance evaluation → route to generate or rewrite
    builder.add_conditional_edges(
        "evaluate_relevance",
        route_by_relevance,
        {"generate_answer": "generate_answer", "rewrite_query": "rewrite_query"},
    )

    # After rewrite → try hybrid retrieval again
    builder.add_edge("rewrite_query", "hybrid_retrieve")

    # DRIFT goes straight to generation (it's already doing self-correction internally)
    builder.add_edge("drift_retrieve", "generate_answer")

    # Done
    builder.add_edge("generate_answer", END)

    checkpointer = InMemorySaver()  # swap for AsyncPostgresSaver in production
    return builder.compile(checkpointer=checkpointer)

"""
agent.py
~~~~~~~~
LangGraph StateGraph for the data pipeline sentinel.
Uses episodic memory (Store) to learn from past drift events.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, Literal

import pandas as pd
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from pydantic import BaseModel
from typing_extensions import TypedDict

from .analysis.schema_diff import compute_schema_diff
from .analysis.statistical import detect_statistical_drift
from .expectations import update_expectation_suite
from .memory import SentinelMemory

logger = logging.getLogger(__name__)


# ── State ──────────────────────────────────────────────────────────────────────

class SentinelState(TypedDict):
    messages: Annotated[list, add_messages]

    # Input
    source_name: str
    current_batch: dict[str, Any]   # Serialized DataFrame stats
    reference_stats: dict[str, Any]  # Previous batch stats

    # Analysis results
    schema_diff: dict[str, Any]
    statistical_anomalies: list[dict]
    relevant_memories: list[dict]

    # Decision
    severity: Literal["OK", "LOW", "MEDIUM", "HIGH"]
    actions_taken: list[str]
    summary: str


# ── Nodes ─────────────────────────────────────────────────────────────────────

def get_llm() -> ChatAnthropic:
    return ChatAnthropic(model="claude-sonnet-4-6", temperature=0, max_tokens=2048)


async def detect_anomalies(state: SentinelState) -> dict:
    """Compute schema diff and statistical drift between batches."""
    schema_diff_result = await compute_schema_diff(
        state["reference_stats"].get("schema", {}),
        state["current_batch"].get("schema", {}),
    )
    statistical_anomalies = await detect_statistical_drift(
        state["reference_stats"].get("stats", {}),
        state["current_batch"].get("stats", {}),
    )

    logger.info(
        "Source %s: %d schema changes, %d statistical anomalies",
        state["source_name"],
        len(schema_diff_result.get("changes", [])),
        len(statistical_anomalies),
    )

    return {
        "schema_diff": schema_diff_result,
        "statistical_anomalies": statistical_anomalies,
    }


async def recall_history(state: SentinelState, store: BaseStore) -> dict:
    """Search episodic memory for similar past events on this data source."""
    # Build a description of the current anomaly for semantic search
    changes = state["schema_diff"].get("changes", [])
    anomalies = state["statistical_anomalies"]

    query_parts = []
    if changes:
        query_parts.append(f"schema drift: {', '.join(c.get('description', '') for c in changes[:3])}")
    if anomalies:
        query_parts.append(f"statistical anomaly: {', '.join(a.get('column', '') for a in anomalies[:3])}")

    if not query_parts:
        return {"relevant_memories": []}

    query = "; ".join(query_parts)
    namespace = ("sentinel", state["source_name"])

    memories = store.search(namespace, query=query, limit=5)
    relevant = [m.value for m in memories]

    logger.info("Recalled %d relevant memories for %s", len(relevant), state["source_name"])
    return {"relevant_memories": relevant}


async def classify_severity(state: SentinelState) -> dict:
    """Use LLM + past experience to classify anomaly severity."""
    llm = get_llm()

    changes = state["schema_diff"].get("changes", [])
    anomalies = state["statistical_anomalies"]

    if not changes and not anomalies:
        return {"severity": "OK", "summary": "No anomalies detected."}

    class SeverityResult(BaseModel):
        severity: Literal["LOW", "MEDIUM", "HIGH"]
        reasoning: str
        recommended_actions: list[str]

    structured_llm = llm.with_structured_output(SeverityResult)

    memories_text = "\n".join(
        f"- {m.get('timestamp', '')}: {m.get('event_type', '')} → {m.get('outcome', '')}"
        for m in state["relevant_memories"][:3]
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a data quality expert classifying data pipeline anomalies.
Severity levels:
- LOW: Minor changes, expected seasonal variation, no downstream impact
- MEDIUM: Schema changes or moderate drift, needs investigation, no immediate outage
- HIGH: Breaking schema changes, severe drift, likely causing downstream failures

Use past incident history to calibrate your assessment."""),
        ("human", """Source: {source}

Schema changes:
{schema_changes}

Statistical anomalies:
{statistical}

Past incidents for this source:
{memories}

Classify severity and recommend actions."""),
    ])

    result = await (prompt | structured_llm).ainvoke({
        "source": state["source_name"],
        "schema_changes": json.dumps(changes, indent=2),
        "statistical": json.dumps(anomalies, indent=2),
        "memories": memories_text or "No past incidents found.",
    })

    return {
        "severity": result.severity,
        "summary": result.reasoning,
    }


async def take_actions(state: SentinelState, store: BaseStore) -> dict:
    """Execute appropriate actions based on severity."""
    severity = state["severity"]
    source = state["source_name"]
    actions_taken = []

    if severity == "OK":
        return {"actions_taken": []}

    # Always update expectations for schema changes
    if state["schema_diff"].get("changes"):
        await update_expectation_suite(source, state["schema_diff"])
        actions_taken.append("updated_great_expectations_suite")

    if severity in ("MEDIUM", "HIGH"):
        # File a GitHub issue
        issue_title = f"[Data Sentinel] {severity} anomaly in {source}"
        issue_body = f"""**Source:** {source}
**Severity:** {severity}
**Detected:** {state['schema_diff'].get('changes', [])}
**Statistical anomalies:** {state['statistical_anomalies'][:3]}
**Analysis:** {state['summary']}
"""
        # In production: file via PyGithub
        logger.info("Would file GitHub issue: %s", issue_title)
        actions_taken.append(f"filed_github_issue: {issue_title}")

    if severity == "HIGH":
        # Trigger DAG rerun
        logger.info("Would trigger Airflow DAG rerun for source: %s", source)
        actions_taken.append(f"triggered_dag_rerun: {source}")

    # Store this event in episodic memory
    memory = SentinelMemory(store=store)
    await memory.store_event(
        source=source,
        event_type="schema_drift" if state["schema_diff"].get("changes") else "statistical_drift",
        severity=severity,
        changes=state["schema_diff"].get("changes", []),
        resolution=", ".join(actions_taken),
        summary=state["summary"],
    )
    actions_taken.append("stored_in_episodic_memory")

    return {"actions_taken": actions_taken}


# ── Graph ─────────────────────────────────────────────────────────────────────

def build_sentinel_graph(store: BaseStore | None = None):
    if store is None:
        store = InMemoryStore()

    async def _recall_history(state: SentinelState) -> dict:
        return await recall_history(state, store)

    async def _take_actions(state: SentinelState) -> dict:
        return await take_actions(state, store)

    builder = StateGraph(SentinelState)
    builder.add_node("detect_anomalies", detect_anomalies)
    builder.add_node("recall_history", _recall_history)
    builder.add_node("classify_severity", classify_severity)
    builder.add_node("take_actions", _take_actions)

    builder.add_edge(START, "detect_anomalies")
    builder.add_edge("detect_anomalies", "recall_history")
    builder.add_edge("recall_history", "classify_severity")
    builder.add_edge("classify_severity", "take_actions")
    builder.add_edge("take_actions", END)

    from langgraph.checkpoint.memory import InMemorySaver
    return builder.compile(checkpointer=InMemorySaver(), store=store)

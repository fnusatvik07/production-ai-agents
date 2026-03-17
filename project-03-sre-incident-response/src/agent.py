"""
agent.py
~~~~~~~~
LangGraph StateGraph for SRE incident response.

Nodes:
  triage_alert → retrieve_runbook → plan_execution →
  execute_step (loop with HITL interrupt) → write_postmortem
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import interrupt, Command
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from pydantic import BaseModel
from typing_extensions import TypedDict

from .config import settings
from .runbook_store import RunbookStore

logger = logging.getLogger(__name__)


# ── State ──────────────────────────────────────────────────────────────────────

class IncidentState(TypedDict):
    messages: Annotated[list, add_messages]

    # Alert context
    alert_name: str
    service: str
    severity: str
    labels: dict[str, str]

    # Runbook and plan
    runbook_text: str
    execution_plan: list[dict]  # [{step, tool, command, dangerous}]
    current_step: int

    # Execution tracking
    step_results: list[dict]
    approved_commands: list[str]

    # Resolution
    resolved: bool
    postmortem: str


# ── LLM ───────────────────────────────────────────────────────────────────────

def get_llm() -> ChatAnthropic:
    return ChatAnthropic(
        model="claude-sonnet-4-6",
        api_key=settings.anthropic_api_key,
        temperature=0,
        max_tokens=4096,
    )


# ── MCP Tool Loading ──────────────────────────────────────────────────────────

async def load_all_mcp_tools() -> list:
    """Load tools from all three MCP servers."""
    all_tools = []

    for name, url in [
        ("kubectl", settings.kubectl_mcp_url),
        ("aws", settings.aws_mcp_url),
        ("http_check", settings.http_check_mcp_url),
    ]:
        try:
            async with streamablehttp_client(url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await load_mcp_tools(session)
                    all_tools.extend(tools)
                    logger.info("Loaded %d tools from %s MCP server", len(tools), name)
        except Exception as e:
            logger.warning("Could not connect to %s MCP server at %s: %s", name, url, e)

    return all_tools


# ── Nodes ─────────────────────────────────────────────────────────────────────

async def triage_alert(state: IncidentState) -> dict:
    """Classify alert severity and determine response urgency."""
    llm = get_llm()

    class TriageResult(BaseModel):
        urgency: Literal["immediate", "high", "medium", "low"]
        affected_components: list[str]
        likely_cause: str
        initial_checks: list[str]

    structured_llm = llm.with_structured_output(TriageResult)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an SRE triaging an alert. Classify urgency and suggest initial diagnostic checks."),
        ("human", "Alert: {alert_name}\nService: {service}\nSeverity: {severity}\nLabels: {labels}"),
    ])

    result = await (prompt | structured_llm).ainvoke({
        "alert_name": state["alert_name"],
        "service": state["service"],
        "severity": state["severity"],
        "labels": json.dumps(state["labels"]),
    })

    logger.info("Triage: %s urgency, likely cause: %s", result.urgency, result.likely_cause)

    return {
        "messages": [
            AIMessage(content=f"Alert triaged as {result.urgency}. Likely: {result.likely_cause}")
        ]
    }


async def retrieve_runbook(state: IncidentState, runbook_store: RunbookStore) -> dict:
    """RAG-retrieve the most relevant runbook for this alert."""
    query = f"{state['alert_name']} {state['service']} {state['severity']}"
    runbook = await runbook_store.retrieve(query)

    logger.info("Retrieved runbook: %d chars", len(runbook))
    return {"runbook_text": runbook}


async def plan_execution(state: IncidentState) -> dict:
    """Convert runbook into a structured execution plan."""
    llm = get_llm()

    class Step(BaseModel):
        step: int
        description: str
        tool: str
        command: str
        dangerous: bool
        danger_reason: str | None = None

    class ExecutionPlan(BaseModel):
        steps: list[Step]
        estimated_resolution: str

    structured_llm = llm.with_structured_output(ExecutionPlan)

    prompt = ChatPromptTemplate.from_messages([
        ("system", """Convert this runbook into a structured execution plan for the current alert.
Available tools: kubectl_get, kubectl_describe, kubectl_top_pods, kubectl_logs,
                 kubectl_rollout_status, kubectl_delete_pod, kubectl_rollout_restart,
                 check_http_endpoint, aws_describe_instance, aws_cloudwatch_metrics

Mark steps as dangerous=true if they: delete/restart pods, modify config, scale services.
Return max 10 steps."""),
        ("human", "Alert: {alert_name} on {service}\n\nRunbook:\n{runbook}"),
    ])

    result = await (prompt | structured_llm).ainvoke({
        "alert_name": state["alert_name"],
        "service": state["service"],
        "runbook": state["runbook_text"][:3000],
    })

    plan = [s.model_dump() for s in result.steps]
    logger.info("Planned %d steps, %d dangerous", len(plan), sum(1 for s in plan if s["dangerous"]))

    return {
        "execution_plan": plan,
        "current_step": 0,
        "step_results": [],
    }


async def execute_step(state: IncidentState) -> dict | Command:
    """
    Execute the current plan step.
    If the step is dangerous, interrupt() to get human approval.
    """
    step_idx = state["current_step"]
    plan = state["execution_plan"]

    if step_idx >= len(plan):
        return {"resolved": True}

    step = plan[step_idx]
    logger.info("Executing step %d/%d: %s", step_idx + 1, len(plan), step["description"])

    # HITL: interrupt on dangerous steps
    if step["dangerous"]:
        decision = interrupt({
            "kind": "approval_required",
            "step": step_idx + 1,
            "total_steps": len(plan),
            "description": step["description"],
            "tool": step["tool"],
            "command": step["command"],
            "danger_reason": step.get("danger_reason", "Destructive operation"),
            "instructions": "Approve, reject, or provide an edited command.",
        })

        if decision.get("choice") == "reject":
            result = {
                "status": "rejected_by_human",
                "step": step_idx,
                "command": step["command"],
            }
            return Command(
                update={
                    "step_results": state["step_results"] + [result],
                    "current_step": step_idx + 1,
                },
            )
        elif decision.get("choice") == "edit":
            step["command"] = decision.get("edited_command", step["command"])

    # Execute the step (here simulated; in production would call MCP tools)
    result = {
        "step": step_idx,
        "description": step["description"],
        "command": step["command"],
        "status": "success",
        "output": f"[Simulated] Executed: {step['command']}",
        "approved": step["dangerous"] and decision.get("choice") == "approve" if step["dangerous"] else True,
    }

    return {
        "step_results": state["step_results"] + [result],
        "current_step": step_idx + 1,
        "messages": [AIMessage(content=f"Step {step_idx + 1}: {step['description']} — OK")],
    }


async def write_postmortem(state: IncidentState) -> dict:
    """Auto-generate a structured postmortem from the execution trace."""
    llm = get_llm()

    steps_text = "\n".join(
        f"- Step {r['step'] + 1}: {r['description']} → {r['status']}"
        + (f" (human approved)" if r.get("approved") else "")
        for r in state["step_results"]
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", "Write a blameless postmortem for this incident. Include timeline, root cause analysis, and action items. Use markdown."),
        ("human", "Alert: {alert_name}\nService: {service}\nSteps executed:\n{steps}\n\nRunbook used:\n{runbook}"),
    ])

    response = await (prompt | llm).ainvoke({
        "alert_name": state["alert_name"],
        "service": state["service"],
        "steps": steps_text,
        "runbook": state["runbook_text"][:1000],
    })

    return {"postmortem": response.content}


# ── Routing ───────────────────────────────────────────────────────────────────

def continue_or_done(state: IncidentState) -> Literal["execute_step", "write_postmortem"]:
    if state.get("resolved") or state["current_step"] >= len(state["execution_plan"]):
        return "write_postmortem"
    return "execute_step"


# ── Graph ─────────────────────────────────────────────────────────────────────

def build_graph(runbook_store: RunbookStore):
    async def _retrieve_runbook(state: IncidentState) -> dict:
        return await retrieve_runbook(state, runbook_store)

    builder = StateGraph(IncidentState)

    builder.add_node("triage_alert", triage_alert)
    builder.add_node("retrieve_runbook", _retrieve_runbook)
    builder.add_node("plan_execution", plan_execution)
    builder.add_node("execute_step", execute_step)
    builder.add_node("write_postmortem", write_postmortem)

    builder.add_edge(START, "triage_alert")
    builder.add_edge("triage_alert", "retrieve_runbook")
    builder.add_edge("retrieve_runbook", "plan_execution")
    builder.add_edge("plan_execution", "execute_step")
    builder.add_conditional_edges("execute_step", continue_or_done)
    builder.add_edge("write_postmortem", END)

    # Use AsyncPostgresSaver in production:
    # from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    # checkpointer = AsyncPostgresSaver.from_conn_string(settings.postgres_uri)
    from langgraph.checkpoint.memory import InMemorySaver
    checkpointer = InMemorySaver()

    return builder.compile(checkpointer=checkpointer)

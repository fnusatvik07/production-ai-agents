"""
api.py
~~~~~~
FastAPI server for the SRE incident response agent.
Handles alert ingestion, human approval, and incident status.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from langgraph.types import Command
from pydantic import BaseModel

from .agent import build_graph
from .runbook_store import RunbookStore

logger = logging.getLogger(__name__)

# Shared graph and active incidents
_graph = None
_active_threads: dict[str, dict] = {}


async def get_graph():
    global _graph
    if _graph is None:
        store = RunbookStore()
        _graph = build_graph(store)
    return _graph


app = FastAPI(
    title="SRE Incident Response Agent",
    description="LangGraph-powered runbook execution with human-in-the-loop approval",
    version="0.1.0",
)


# ── Models ─────────────────────────────────────────────────────────────────────

class AlertPayload(BaseModel):
    alert_name: str
    service: str
    severity: Literal["critical", "high", "medium", "low"]
    labels: dict[str, str] = {}


class ApprovalRequest(BaseModel):
    decision: Literal["approve", "reject", "edit"]
    edited_command: str | None = None


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.post("/alert")
async def receive_alert(alert: AlertPayload):
    """Receive an alert and start an incident response."""
    thread_id = f"incident-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}
    graph = await get_graph()

    initial_state = {
        "messages": [],
        "alert_name": alert.alert_name,
        "service": alert.service,
        "severity": alert.severity,
        "labels": alert.labels,
        "runbook_text": "",
        "execution_plan": [],
        "current_step": 0,
        "step_results": [],
        "approved_commands": [],
        "resolved": False,
        "postmortem": "",
    }

    _active_threads[thread_id] = {"status": "running", "alert": alert.model_dump()}

    try:
        result = await graph.ainvoke(initial_state, config=config)
        _active_threads[thread_id]["status"] = "awaiting_approval" if "__interrupt__" in result else "completed"
        _active_threads[thread_id]["state"] = result

        if "__interrupt__" in result:
            interrupt_data = result["__interrupt__"][0].value
            return {
                "thread_id": thread_id,
                "status": "awaiting_approval",
                "pending_action": interrupt_data,
            }

        return {
            "thread_id": thread_id,
            "status": "completed",
            "steps_executed": len(result.get("step_results", [])),
            "postmortem_preview": result.get("postmortem", "")[:300],
        }

    except Exception as e:
        logger.exception("Incident response failed for alert %s", alert.alert_name)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/approve/{thread_id}")
async def approve_action(thread_id: str, approval: ApprovalRequest):
    """Resume a paused incident after human approval/rejection."""
    if thread_id not in _active_threads:
        raise HTTPException(status_code=404, detail="Incident not found")

    graph = await get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    resume_value = {"choice": approval.decision}
    if approval.decision == "edit" and approval.edited_command:
        resume_value["edited_command"] = approval.edited_command

    try:
        result = await graph.ainvoke(
            Command(resume=resume_value),
            config=config,
        )

        if "__interrupt__" in result:
            interrupt_data = result["__interrupt__"][0].value
            _active_threads[thread_id]["status"] = "awaiting_approval"
            return {
                "thread_id": thread_id,
                "status": "awaiting_approval",
                "pending_action": interrupt_data,
            }

        _active_threads[thread_id]["status"] = "completed"
        return {
            "thread_id": thread_id,
            "status": "completed",
            "steps_executed": len(result.get("step_results", [])),
            "postmortem": result.get("postmortem", ""),
        }

    except Exception as e:
        logger.exception("Approval handling failed for thread %s", thread_id)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/incident/{thread_id}")
async def get_incident(thread_id: str):
    """Get current state of an incident."""
    if thread_id not in _active_threads:
        raise HTTPException(status_code=404, detail="Incident not found")

    graph = await get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    state = await graph.aget_state(config)

    return {
        "thread_id": thread_id,
        "status": _active_threads[thread_id]["status"],
        "current_step": state.values.get("current_step", 0),
        "total_steps": len(state.values.get("execution_plan", [])),
        "step_results": state.values.get("step_results", []),
        "resolved": state.values.get("resolved", False),
    }


@app.get("/incidents")
async def list_incidents():
    return {
        "incidents": [
            {"thread_id": tid, **info}
            for tid, info in _active_threads.items()
        ]
    }


@app.get("/health")
async def health():
    return {"status": "ok"}

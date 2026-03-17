"""
api.py
~~~~~~
FastAPI server for triggering intelligence runs and fetching results.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any

from autogen_agentchat.messages import TextMessage
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .swarm import build_swarm, load_browser_tools

logger = logging.getLogger(__name__)

_swarm = None
_results_store: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _swarm
    logger.info("Loading browser MCP tools...")
    browser_tools = await load_browser_tools()
    _swarm = build_swarm(os.environ.get("OPENAI_API_KEY", ""), browser_tools)
    logger.info("Competitive Intelligence Swarm ready.")
    yield


app = FastAPI(
    title="Competitive Intelligence Swarm",
    description="LangGraph swarm for competitive intelligence gathering",
    lifespan=lifespan,
)


class IntelligenceRequest(BaseModel):
    competitors: list[str]          # List of competitor domains
    focus_areas: list[str] = ["product", "pricing", "hiring", "patents"]
    session_id: str | None = None


@app.post("/run")
async def run_intelligence(request: IntelligenceRequest):
    """Trigger an intelligence run for specified competitors."""
    session_id = request.session_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}

    competitors_text = "\n".join(f"- {c}" for c in request.competitors)
    task = f"""Analyze these competitors for competitive intelligence:
{competitors_text}

Focus on: {', '.join(request.focus_areas)}
Start with the ProductAgent for the first competitor."""

    logger.info("Starting intelligence run %s for %d competitors", session_id, len(request.competitors))

    try:
        messages = []
        async for chunk in _swarm.astream(
            {"messages": [{"role": "user", "content": task}]},
            config=config,
        ):
            for node_name, node_output in chunk.items():
                if "messages" in node_output:
                    for msg in node_output["messages"]:
                        if hasattr(msg, "content") and msg.content:
                            messages.append({
                                "agent": node_name,
                                "content": msg.content[:2000],
                            })

        # Extract final brief
        final_brief = ""
        for msg in reversed(messages):
            if "BRIEF_COMPLETE" in msg.get("content", "") or msg.get("agent") == "SynthesisAgent":
                final_brief = msg["content"]
                break

        result = {
            "session_id": session_id,
            "competitors": request.competitors,
            "brief": final_brief,
            "agent_messages": messages,
            "message_count": len(messages),
        }

        _results_store[session_id] = result
        return result

    except Exception as e:
        logger.exception("Intelligence run failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/results/{session_id}")
async def get_results(session_id: str):
    """Get results of a past intelligence run."""
    if session_id not in _results_store:
        raise HTTPException(status_code=404, detail="Session not found")
    return _results_store[session_id]


@app.get("/results")
async def list_results():
    """List all past intelligence runs."""
    return {
        "runs": [
            {"session_id": sid, "competitors": r.get("competitors", []), "message_count": r.get("message_count", 0)}
            for sid, r in _results_store.items()
        ]
    }


@app.get("/health")
async def health():
    return {"status": "ok", "swarm": "ready" if _swarm else "not_initialized"}

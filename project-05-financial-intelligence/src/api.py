"""
api.py
~~~~~~
FastAPI server with WebSocket streaming for real-time agent message delivery.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager

from autogen_agentchat.messages import TextMessage
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .observability import setup_phoenix_tracing
from .regime_detector import detect_regime
from .team import build_team

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_phoenix_tracing()
    logger.info("Financial Intelligence API started.")
    yield
    logger.info("Shutdown.")


app = FastAPI(
    title="Financial Intelligence System",
    description="Multi-agent financial analysis with regime-aware routing",
    version="0.1.0",
    lifespan=lifespan,
)


class AnalysisRequest(BaseModel):
    question: str
    session_id: str | None = None


@app.post("/analyze")
async def analyze(request: AnalysisRequest):
    """Run a financial analysis query. Returns full result when complete."""
    import os
    session_id = request.session_id or str(uuid.uuid4())

    # Detect market regime
    regime = await detect_regime()
    logger.info("Regime: %s (%.0f%% confidence)", regime.regime.value, regime.confidence * 100)

    # Build team
    team = build_team(regime, os.environ.get("OPENAI_API_KEY", ""))

    # Run
    messages = []
    async for msg in team.run_stream(task=request.question):
        if isinstance(msg, TextMessage):
            messages.append({
                "agent": msg.source,
                "content": msg.content,
            })

    return {
        "session_id": session_id,
        "regime": regime.regime.value,
        "regime_confidence": regime.confidence,
        "market_signals": regime.signals,
        "messages": messages,
        "answer": messages[-1]["content"] if messages else "",
    }


@app.websocket("/analyze/ws")
async def analyze_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time streaming of agent messages."""
    import os
    await websocket.accept()

    try:
        # Receive the question
        data = await websocket.receive_json()
        question = data.get("question", "")

        if not question:
            await websocket.send_json({"error": "No question provided"})
            await websocket.close()
            return

        # Send regime info first
        regime = await detect_regime()
        await websocket.send_json({
            "type": "regime",
            "regime": regime.regime.value,
            "confidence": regime.confidence,
            "signals": regime.signals,
        })

        # Build and run team, streaming each message
        team = build_team(regime, os.environ.get("OPENAI_API_KEY", ""))

        async for msg in team.run_stream(task=question):
            if isinstance(msg, TextMessage):
                await websocket.send_json({
                    "type": "message",
                    "agent": msg.source,
                    "content": msg.content,
                })

        await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.exception("WebSocket error")
        await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        await websocket.close()


@app.get("/health")
async def health():
    return {"status": "ok"}

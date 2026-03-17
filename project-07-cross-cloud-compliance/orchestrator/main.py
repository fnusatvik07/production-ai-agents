"""
orchestrator/main.py
~~~~~~~~~~~~~~~~~~~~
Compliance orchestrator: receives documents, fans out to A2A compliance agents,
and assembles unified report.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

import httpx
import uvicorn
from a2a.client import A2AClient
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

logger = logging.getLogger(__name__)

AGENT_URLS = {
    "gdpr": os.environ.get("GDPR_AGENT_URL", "http://localhost:8070"),
    "sox": os.environ.get("SOX_AGENT_URL", "http://localhost:8071"),
    "hipaa": os.environ.get("HIPAA_AGENT_URL", "http://localhost:8072"),
}

app = FastAPI(title="Cross-Cloud Compliance Orchestrator")


async def call_compliance_agent(
    http_client: httpx.AsyncClient,
    regulation: str,
    agent_url: str,
    document_text: str,
) -> dict[str, Any]:
    """Call a compliance agent via A2A and return parsed findings."""
    start = time.monotonic()

    try:
        client = await A2AClient.get_client_from_agent_card_url(http_client, agent_url)

        from a2a.types import MessageSendParams
        response = await client.send_message(MessageSendParams(
            message={"role": "user", "parts": [{"kind": "text", "text": document_text}]}
        ))

        raw = ""
        for part in response.result.parts:
            if hasattr(part.root, "text"):
                raw = part.root.text
                break

        try:
            findings = json.loads(raw)
        except json.JSONDecodeError:
            findings = {"regulation": regulation.upper(), "raw": raw, "findings": [], "overall_score": 0}

        findings["latency_ms"] = round((time.monotonic() - start) * 1000, 1)
        return findings

    except Exception as e:
        logger.error("Agent %s failed: %s", regulation, e)
        return {
            "regulation": regulation.upper(),
            "error": str(e),
            "findings": [],
            "overall_score": 0,
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
        }


def merge_findings(agent_results: list[dict]) -> dict[str, Any]:
    """Merge findings from multiple compliance agents into unified report."""
    all_findings = []
    scores = []
    regulations = []

    for result in agent_results:
        reg = result.get("regulation", "UNKNOWN")
        regulations.append(reg)

        score = result.get("overall_score", 0)
        if score > 0:
            scores.append(score)

        for finding in result.get("findings", []):
            finding["regulation"] = reg
            all_findings.append(finding)

    # Sort by severity
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    all_findings.sort(key=lambda f: severity_order.get(f.get("severity", "INFO"), 4))

    overall_score = sum(scores) / len(scores) if scores else 0
    critical_count = sum(1 for f in all_findings if f.get("severity") == "CRITICAL")
    high_count = sum(1 for f in all_findings if f.get("severity") == "HIGH")

    return {
        "regulations_checked": regulations,
        "overall_compliance_score": round(overall_score, 1),
        "compliance_status": (
            "CRITICAL_GAPS" if critical_count > 0
            else "SIGNIFICANT_GAPS" if high_count > 2
            else "MINOR_GAPS" if all_findings
            else "COMPLIANT"
        ),
        "total_findings": len(all_findings),
        "critical_findings": critical_count,
        "high_findings": high_count,
        "findings": all_findings[:50],  # cap for readability
        "agent_results": agent_results,
    }


@app.post("/audit")
async def audit_document(
    file: UploadFile = File(...),
    regulations: str = Form(default='["gdpr", "sox", "hipaa"]'),
):
    """Audit a document against selected compliance regulations."""
    content = await file.read()
    document_text = content.decode("utf-8", errors="ignore")

    if len(document_text) < 100:
        raise HTTPException(status_code=400, detail="Document too short or unreadable")

    try:
        reg_list = json.loads(regulations)
    except json.JSONDecodeError:
        reg_list = ["gdpr", "sox", "hipaa"]

    # Filter to valid agents
    selected_agents = {k: v for k, v in AGENT_URLS.items() if k in reg_list}

    logger.info("Auditing document: %d chars against %s", len(document_text), list(selected_agents.keys()))

    async with httpx.AsyncClient(timeout=180.0) as http_client:
        tasks = [
            call_compliance_agent(http_client, reg, url, document_text[:8000])
            for reg, url in selected_agents.items()
        ]
        results = await asyncio.gather(*tasks)

    report = merge_findings(list(results))
    report["document_name"] = file.filename
    report["document_length"] = len(document_text)

    return report


@app.get("/health")
async def health():
    return {"status": "ok", "agents": list(AGENT_URLS.keys())}


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("ORCHESTRATOR_PORT", "8007")))

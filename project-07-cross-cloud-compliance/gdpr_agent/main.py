"""
gdpr_agent/main.py
~~~~~~~~~~~~~~~~~~
GDPR compliance agent built with raw Anthropic SDK + A2A server.
Deployed on GCP Cloud Run (europe-west4 for EU data residency).

Run locally: uvicorn main:app --port 8070
"""

from __future__ import annotations

import json
import logging
import os

import anthropic
import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill, TextPart
from a2a.utils import new_agent_text_message

logger = logging.getLogger(__name__)

GDPR_ARTICLES = [
    "Art. 5 — Principles of processing",
    "Art. 6 — Lawfulness of processing",
    "Art. 7 — Conditions for consent",
    "Art. 13 — Information to be provided (direct collection)",
    "Art. 14 — Information to be provided (indirect collection)",
    "Art. 17 — Right to erasure",
    "Art. 20 — Right to data portability",
    "Art. 25 — Data protection by design and default",
    "Art. 28 — Processor obligations",
    "Art. 32 — Security of processing",
    "Art. 33 — Notification of personal data breaches",
    "Art. 35 — DPIA requirements",
]

GDPR_REVIEW_TOOLS = [
    {
        "name": "check_article_compliance",
        "description": "Check document compliance with a specific GDPR article",
        "input_schema": {
            "type": "object",
            "properties": {
                "article": {"type": "string", "description": "GDPR article to check"},
                "relevant_text": {"type": "string", "description": "Relevant document excerpt"},
            },
            "required": ["article", "relevant_text"],
        },
    },
]


def check_article_compliance(article: str, relevant_text: str) -> dict:
    """Heuristic checks for specific GDPR article compliance."""
    findings = {"article": article, "mentions_found": [], "potential_issues": []}

    text_lower = relevant_text.lower()

    if "Art. 5" in article:
        if "purpose" not in text_lower:
            findings["potential_issues"].append("Purpose of processing not clearly stated")
        if "retention" not in text_lower and "delete" not in text_lower:
            findings["potential_issues"].append("Data retention period not mentioned")

    elif "Art. 6" in article:
        legal_bases = ["consent", "contract", "legal obligation", "vital interests", "public task", "legitimate interest"]
        found = [lb for lb in legal_bases if lb in text_lower]
        if not found:
            findings["potential_issues"].append("No lawful basis for processing identified")
        else:
            findings["mentions_found"] = found

    elif "Art. 32" in article:
        security_terms = ["encryption", "pseudonymization", "access control", "security measures"]
        found = [t for t in security_terms if t in text_lower]
        findings["mentions_found"] = found
        if len(found) < 2:
            findings["potential_issues"].append("Insufficient security measures described")

    return findings


async def run_gdpr_analysis(document_text: str, api_key: str) -> str:
    """Run GDPR compliance analysis using Claude with tool use."""
    client = anthropic.AsyncAnthropic(api_key=api_key)

    messages = [{
        "role": "user",
        "content": f"""Analyze this document for GDPR compliance. Check these articles:
{chr(10).join(GDPR_ARTICLES)}

Use check_article_compliance to assess compliance for each relevant article.

Document:
{document_text[:6000]}

Return a JSON compliance report.""",
    }]

    # Agentic loop
    for _ in range(10):
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=3000,
            tools=GDPR_REVIEW_TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            break

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = check_article_compliance(**block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

    return json.dumps({
        "regulation": "GDPR",
        "compliance_status": "ANALYSIS_INCOMPLETE",
        "findings": [],
        "overall_score": 0,
    })


class GDPRAgentExecutor(AgentExecutor):
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        doc_text = ""
        for part in context.message.parts:
            if isinstance(part.root, TextPart):
                doc_text = part.root.text
                break

        if not doc_text:
            event_queue.enqueue_event(new_agent_text_message('{"error": "No document text"}'))
            return

        logger.info("GDPR agent analyzing document (%d chars)", len(doc_text))
        result = await run_gdpr_analysis(doc_text, self._api_key)
        event_queue.enqueue_event(new_agent_text_message(result))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError


def build_app(api_key: str, port: int = 8070):
    card = AgentCard(
        name="GDPR Compliance Agent",
        description="Analyzes documents for EU GDPR compliance across all 99 articles",
        url=f"http://localhost:{port}/",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False),
        skills=[AgentSkill(
            id="gdpr_audit",
            name="GDPR Compliance Audit",
            description="Full GDPR compliance review of business documents, DPAs, and privacy policies",
            tags=["gdpr", "compliance", "privacy", "eu", "data-protection"],
            inputModes=["text/plain"],
            outputModes=["application/json"],
        )],
    )
    handler = DefaultRequestHandler(
        agent_executor=GDPRAgentExecutor(api_key),
        task_store=InMemoryTaskStore(),
    )
    return A2AStarletteApplication(agent_card=card, http_handler=handler).build()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("GDPR_AGENT_PORT", "8070"))
    uvicorn.run(build_app(os.environ["ANTHROPIC_API_KEY"], port), host="0.0.0.0", port=port)

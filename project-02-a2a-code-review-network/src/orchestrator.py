"""
orchestrator.py
~~~~~~~~~~~~~~~
A2A client that fans out code review tasks to all specialist agents in parallel,
collects findings as artifacts, deduplicates, and assembles the final review.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
from a2a.client import A2AClient
from a2a.types import MessageSendParams, Part, TextPart

logger = logging.getLogger(__name__)

AGENT_URLS = {
    "security": "http://localhost:8010",
    "style": "http://localhost:8011",
    "test": "http://localhost:8012",
}


@dataclass
class AgentReview:
    agent_name: str
    findings: list[dict]
    summary: str
    latency_ms: float
    raw_response: str


# ── Agent Card Cache ───────────────────────────────────────────────────────────

_card_cache: dict[str, tuple[Any, float]] = {}
CARD_TTL_SECONDS = 300


async def fetch_agent_card(http_client: httpx.AsyncClient, url: str) -> Any:
    """Fetch and cache agent card from /.well-known/agent.json"""
    cached = _card_cache.get(url)
    if cached and (time.time() - cached[1]) < CARD_TTL_SECONDS:
        return cached[0]

    client = await A2AClient.get_client_from_agent_card_url(http_client, url)
    _card_cache[url] = (client, time.time())
    return client


# ── Per-Agent Review ───────────────────────────────────────────────────────────

async def call_specialist_agent(
    http_client: httpx.AsyncClient,
    agent_name: str,
    agent_url: str,
    diff: str,
) -> AgentReview:
    """Call a single specialist agent and parse its findings."""
    start = time.monotonic()

    try:
        client = await fetch_agent_card(http_client, agent_url)

        params = MessageSendParams(
            message={
                "role": "user",
                "parts": [{"kind": "text", "text": diff}],
            }
        )
        response = await client.send_message(params)
        latency_ms = (time.monotonic() - start) * 1000

        # Extract text from response
        raw = ""
        for part in response.result.parts:
            if hasattr(part.root, "text"):
                raw = part.root.text
                break

        # Try to parse JSON findings
        try:
            parsed = json.loads(raw)
            findings = parsed.get("findings", [])
            summary = parsed.get("summary", "")
        except json.JSONDecodeError:
            findings = []
            summary = raw[:200]

        logger.info(
            "%s agent: %d findings in %.0fms",
            agent_name, len(findings), latency_ms,
        )
        return AgentReview(
            agent_name=agent_name,
            findings=findings,
            summary=summary,
            latency_ms=latency_ms,
            raw_response=raw,
        )

    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        logger.error("Agent %s failed: %s", agent_name, e)
        return AgentReview(
            agent_name=agent_name,
            findings=[],
            summary=f"Agent failed: {e}",
            latency_ms=latency_ms,
            raw_response="",
        )


# ── Orchestration ──────────────────────────────────────────────────────────────

async def orchestrate_review(diff: str) -> dict[str, Any]:
    """
    Fan out diff to all specialist agents in parallel via A2A.
    Returns aggregated review report.
    """
    async with httpx.AsyncClient(timeout=120.0) as http_client:
        # All three agents called concurrently
        tasks = [
            call_specialist_agent(http_client, name, url, diff)
            for name, url in AGENT_URLS.items()
        ]
        reviews: list[AgentReview] = await asyncio.gather(*tasks)

    # Aggregate findings
    all_findings = []
    agent_summaries = {}
    total_latency = max(r.latency_ms for r in reviews)  # parallel, so max not sum

    for review in reviews:
        agent_summaries[review.agent_name] = {
            "summary": review.summary,
            "finding_count": len(review.findings),
            "latency_ms": round(review.latency_ms, 1),
        }
        for finding in review.findings:
            finding["agent"] = review.agent_name
            all_findings.append(finding)

    # Deduplicate by description similarity (naive: exact match on first 80 chars)
    seen_descriptions: set[str] = set()
    unique_findings = []
    for f in all_findings:
        desc_key = f.get("description", "")[:80]
        if desc_key not in seen_descriptions:
            seen_descriptions.add(desc_key)
            unique_findings.append(f)

    # Sort by severity
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    unique_findings.sort(
        key=lambda f: severity_order.get(f.get("severity", "INFO"), 4)
    )

    critical_count = sum(1 for f in unique_findings if f.get("severity") == "CRITICAL")
    high_count = sum(1 for f in unique_findings if f.get("severity") == "HIGH")

    return {
        "total_findings": len(unique_findings),
        "critical": critical_count,
        "high": high_count,
        "findings": unique_findings,
        "agent_summaries": agent_summaries,
        "overall_risk": "CRITICAL" if critical_count > 0 else "HIGH" if high_count > 0 else "MEDIUM",
        "total_latency_ms": round(total_latency, 1),
        "review_id": f"review_{int(time.time())}",
    }


def format_github_comment(review: dict) -> str:
    """Format the aggregated review as a GitHub PR comment in Markdown."""
    risk_emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(
        review["overall_risk"], "⚪"
    )

    lines = [
        "## 🤖 AI Code Review",
        f"",
        f"**Overall Risk:** {risk_emoji} {review['overall_risk']}  ",
        f"**Total Findings:** {review['total_findings']} ({review['critical']} critical, {review['high']} high)  ",
        f"**Review Time:** {review['total_latency_ms']}ms (parallel)  ",
        f"",
        "### Findings",
        "",
    ]

    for finding in review["findings"][:20]:  # cap at 20 for readability
        severity = finding.get("severity", "INFO")
        emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢", "INFO": "ℹ️"}.get(severity, "⚪")
        agent = finding.get("agent", "unknown")
        lines.append(f"- {emoji} **[{severity}]** `{agent}`: {finding.get('description', '')}")
        if finding.get("recommendation"):
            lines.append(f"  > 💡 {finding['recommendation']}")

    lines.extend([
        "",
        "### Agent Summaries",
        "",
    ])

    for agent_name, summary in review["agent_summaries"].items():
        lines.append(f"- **{agent_name}** ({summary['finding_count']} findings, {summary['latency_ms']}ms): {summary['summary']}")

    lines.extend([
        "",
        f"---",
        f"*Reviewed by Security ({AGENT_URLS['security']}), Style ({AGENT_URLS['style']}), and Test ({AGENT_URLS['test']}) agents via A2A protocol*",
    ])

    return "\n".join(lines)

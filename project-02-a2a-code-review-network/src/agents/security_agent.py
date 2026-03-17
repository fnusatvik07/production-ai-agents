"""
security_agent.py
~~~~~~~~~~~~~~~~~
A2A server wrapping a LangGraph security review agent.

Skills:
  - security_review: Finds OWASP Top 10 vulnerabilities, secrets, injection flaws

Run: uv run python -m src.agents.security_agent
"""

from __future__ import annotations

import json
import logging
from typing import Any

import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    DataPart,
    TextPart,
)
from a2a.utils import new_agent_text_message
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ── Security Review Tools ──────────────────────────────────────────────────────

OWASP_TOP_10 = [
    "A01:2021 Broken Access Control",
    "A02:2021 Cryptographic Failures",
    "A03:2021 Injection",
    "A04:2021 Insecure Design",
    "A05:2021 Security Misconfiguration",
    "A06:2021 Vulnerable and Outdated Components",
    "A07:2021 Identification and Authentication Failures",
    "A08:2021 Software and Data Integrity Failures",
    "A09:2021 Security Logging and Monitoring Failures",
    "A10:2021 Server-Side Request Forgery (SSRF)",
]

@tool
def check_injection_patterns(code: str) -> str:
    """Check code for common injection vulnerability patterns."""
    patterns = {
        "SQL Injection": [
            "f\"SELECT", "f'SELECT", "% (", "format(", "+user_input",
            "execute(query", ".format(user",
        ],
        "Command Injection": [
            "os.system(", "subprocess.call(", "shell=True",
            "eval(", "exec(",
        ],
        "Path Traversal": [
            "../", "..\\", "os.path.join(user",
        ],
        "Hardcoded Secrets": [
            "password =", "secret =", "api_key =", "AWS_SECRET",
            "token = \"", "password=\"",
        ],
    }

    findings = []
    for vuln_type, markers in patterns.items():
        for marker in markers:
            if marker.lower() in code.lower():
                findings.append(f"Potential {vuln_type}: found pattern '{marker}'")

    if not findings:
        return "No injection patterns detected in static analysis."
    return "\n".join(findings)


@tool
def check_authentication_issues(code: str) -> str:
    """Check for authentication and authorization weaknesses."""
    issues = []

    weak_patterns = [
        ("MD5 hashing", ["md5(", "hashlib.md5"]),
        ("SHA1 hashing (weak)", ["sha1(", "hashlib.sha1"]),
        ("Hardcoded JWT secret", ["SECRET_KEY = \"", "JWT_SECRET = \""]),
        ("Missing HTTPS enforcement", ["http://", "verify=False"]),
        ("Insecure cookie", ["httponly=False", "secure=False", "samesite=None"]),
    ]

    for issue_name, patterns in weak_patterns:
        for pattern in patterns:
            if pattern.lower() in code.lower():
                issues.append(f"Auth issue: {issue_name} (pattern: '{pattern}')")

    return "\n".join(issues) if issues else "No authentication issues detected."


# ── LangGraph Security Agent ──────────────────────────────────────────────────

def build_security_graph(api_key: str):
    llm = ChatAnthropic(
        model="claude-sonnet-4-6",
        api_key=api_key,
        temperature=0,
    )
    agent = create_react_agent(
        llm,
        tools=[check_injection_patterns, check_authentication_issues],
        state_modifier="""You are a security code reviewer specializing in OWASP Top 10 vulnerabilities.

For each code diff, you MUST:
1. Use check_injection_patterns to detect injection vulnerabilities
2. Use check_authentication_issues to check auth/authz weaknesses
3. Analyze the code for any other security concerns

Always return a JSON object with this exact structure:
{
  "findings": [
    {
      "severity": "CRITICAL|HIGH|MEDIUM|LOW|INFO",
      "category": "OWASP category",
      "line": "affected line or null",
      "description": "what the vulnerability is",
      "recommendation": "how to fix it"
    }
  ],
  "overall_risk": "CRITICAL|HIGH|MEDIUM|LOW",
  "summary": "one-sentence summary"
}""",
    )
    return agent


# ── A2A Agent Executor ────────────────────────────────────────────────────────

class SecurityAgentExecutor(AgentExecutor):
    def __init__(self, api_key: str) -> None:
        self._graph = build_security_graph(api_key)

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # Extract diff text from incoming message
        diff_text = ""
        for part in context.message.parts:
            if isinstance(part.root, TextPart):
                diff_text = part.root.text
                break

        if not diff_text:
            event_queue.enqueue_event(
                new_agent_text_message('{"error": "No code diff provided"}')
            )
            return

        logger.info("Security agent analyzing diff (%d chars)", len(diff_text))

        result = await self._graph.ainvoke({
            "messages": [HumanMessage(content=f"Review this code diff for security vulnerabilities:\n\n{diff_text}")]
        })

        # Extract the final message
        final_message = result["messages"][-1].content
        event_queue.enqueue_event(new_agent_text_message(final_message))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError


# ── A2A Server Setup ──────────────────────────────────────────────────────────

def build_app(api_key: str, port: int = 8010):
    agent_card = AgentCard(
        name="Security Review Agent",
        description="Analyzes code diffs for OWASP Top 10 vulnerabilities, injection flaws, and secrets exposure",
        url=f"http://localhost:{port}/",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="security_review",
                name="Security Code Review",
                description="Finds security vulnerabilities: SQL injection, XSS, hardcoded secrets, weak crypto, path traversal",
                tags=["security", "vulnerability", "owasp", "injection"],
                inputModes=["text/plain"],
                outputModes=["application/json"],
            )
        ],
    )

    handler = DefaultRequestHandler(
        agent_executor=SecurityAgentExecutor(api_key),
        task_store=InMemoryTaskStore(),
    )
    app = A2AStarletteApplication(agent_card=agent_card, http_handler=handler)
    return app.build()


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.environ["ANTHROPIC_API_KEY"]
    port = int(os.environ.get("SECURITY_AGENT_PORT", "8010"))

    logging.basicConfig(level=logging.INFO)
    logger.info("Starting Security Review Agent on port %d", port)

    uvicorn.run(build_app(api_key, port), host="0.0.0.0", port=port)

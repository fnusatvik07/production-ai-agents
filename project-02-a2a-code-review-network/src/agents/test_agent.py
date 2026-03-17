"""
test_agent.py
~~~~~~~~~~~~~
A2A server wrapping a raw Anthropic SDK test coverage agent.

Skills:
  - test_review: Identifies missing test cases, uncovered edge cases, test quality

Run: uv run python -m src.agents.test_agent
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

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


# ── Raw Anthropic Agentic Loop ────────────────────────────────────────────────

TEST_ANALYSIS_TOOLS = [
    {
        "name": "analyze_function_complexity",
        "description": "Analyze a function's cyclomatic complexity and identify branches that need testing",
        "input_schema": {
            "type": "object",
            "properties": {
                "function_code": {
                    "type": "string",
                    "description": "The function code to analyze",
                },
                "function_name": {
                    "type": "string",
                    "description": "Name of the function",
                },
            },
            "required": ["function_code"],
        },
    },
    {
        "name": "suggest_test_cases",
        "description": "Suggest specific test cases for a given function including edge cases",
        "input_schema": {
            "type": "object",
            "properties": {
                "function_signature": {
                    "type": "string",
                    "description": "Function signature and docstring",
                },
                "complexity_notes": {
                    "type": "string",
                    "description": "Notes about complexity and branches from previous analysis",
                },
            },
            "required": ["function_signature"],
        },
    },
]


def dispatch_tool(name: str, inputs: dict) -> str:
    """Local tool implementations (no external calls needed for this agent)."""
    if name == "analyze_function_complexity":
        code = inputs.get("function_code", "")
        # Heuristic: count branches
        branch_count = sum(1 for kw in ["if ", "elif ", "for ", "while ", "except ", "and ", "or "]
                          if kw in code)
        return json.dumps({
            "cyclomatic_complexity": branch_count + 1,
            "branches": branch_count,
            "risk_level": "HIGH" if branch_count > 5 else "MEDIUM" if branch_count > 2 else "LOW",
            "needs_tests_for": [
                "empty/null inputs",
                "boundary values",
                f"each of the {branch_count} conditional branches",
                "exception paths" if "except" in code or "raise" in code else None,
            ],
        })

    elif name == "suggest_test_cases":
        sig = inputs.get("function_signature", "")
        notes = inputs.get("complexity_notes", "")
        return json.dumps({
            "suggested_tests": [
                {"name": "test_happy_path", "description": "Normal inputs, expected output"},
                {"name": "test_empty_input", "description": "Empty string/list/None inputs"},
                {"name": "test_boundary_values", "description": "Min/max values for numeric params"},
                {"name": "test_invalid_type", "description": "Wrong type inputs should raise TypeError"},
                {"name": "test_concurrent_access", "description": "Thread safety if applicable"},
            ],
            "pytest_example": f"def test_{sig.split('(')[0].strip().replace('def ', '')}():\n    # Arrange\n    # Act\n    # Assert\n    pass",
        })

    return json.dumps({"error": f"Unknown tool: {name}"})


async def run_test_review_agent(diff: str, api_key: str) -> str:
    """Run the full agentic loop using raw Anthropic SDK."""
    client = anthropic.AsyncAnthropic(api_key=api_key)

    messages = [
        {
            "role": "user",
            "content": f"""Analyze this code diff and identify:
1. Functions/methods added or modified
2. Their cyclomatic complexity (use analyze_function_complexity tool)
3. Missing test cases (use suggest_test_cases tool)
4. Overall test coverage assessment

Return a final JSON with structure:
{{
  "coverage_assessment": "POOR|FAIR|GOOD",
  "missing_tests": [...],
  "suggested_test_cases": [...],
  "priority_items": [top 3 most important test cases to write],
  "summary": "one-sentence summary"
}}

Code diff:
{diff}""",
        }
    ]

    # Agentic loop
    for _ in range(5):  # max iterations
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            tools=TEST_ANALYSIS_TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            # Extract final text response
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return '{"error": "No text response from agent"}'

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = dispatch_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

    return '{"error": "Agent exceeded max iterations"}'


# ── A2A Agent Executor ────────────────────────────────────────────────────────

class TestAgentExecutor(AgentExecutor):
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
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

        logger.info("Test agent analyzing diff (%d chars)", len(diff_text))
        result = await run_test_review_agent(diff_text, self._api_key)
        event_queue.enqueue_event(new_agent_text_message(result))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError


# ── A2A Server Setup ──────────────────────────────────────────────────────────

def build_app(api_key: str, port: int = 8012):
    agent_card = AgentCard(
        name="Test Coverage Agent",
        description="Analyzes code diffs for missing tests, uncovered edge cases, and test quality using Claude with tool use",
        url=f"http://localhost:{port}/",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="test_review",
                name="Test Coverage Review",
                description="Identifies missing unit tests, edge cases, and suggests specific pytest test cases",
                tags=["testing", "coverage", "pytest", "edge-cases"],
                inputModes=["text/plain"],
                outputModes=["application/json"],
            )
        ],
    )

    handler = DefaultRequestHandler(
        agent_executor=TestAgentExecutor(api_key),
        task_store=InMemoryTaskStore(),
    )
    app_instance = A2AStarletteApplication(agent_card=agent_card, http_handler=handler)
    return app_instance.build()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.environ["ANTHROPIC_API_KEY"]
    port = int(os.environ.get("TEST_AGENT_PORT", "8012"))

    logging.basicConfig(level=logging.INFO)
    logger.info("Starting Test Coverage Agent on port %d", port)
    uvicorn.run(build_app(api_key, port), host="0.0.0.0", port=port)

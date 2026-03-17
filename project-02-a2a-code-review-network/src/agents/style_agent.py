"""
style_agent.py
~~~~~~~~~~~~~~
A2A server wrapping a CrewAI style review crew.

Skills:
  - style_review: Code style, naming, readability, PEP8 conformance

Run: uv run python -m src.agents.style_agent
"""

from __future__ import annotations

import logging
import os

import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill, TextPart
from a2a.utils import new_agent_text_message
from crewai import Agent, Crew, Process, Task
from crewai.llm import LLM

logger = logging.getLogger(__name__)


# ── CrewAI Style Review Crew ──────────────────────────────────────────────────

def build_style_crew(openai_api_key: str) -> Crew:
    llm = LLM(model="gpt-4o", api_key=openai_api_key, temperature=0)

    style_reviewer = Agent(
        role="Senior Code Style Reviewer",
        goal="Identify style issues, naming violations, and readability problems in code diffs",
        backstory="""You are a meticulous code reviewer with 15 years of experience.
You enforce PEP 8 for Python, clean architecture principles, and clear naming conventions.
You focus on maintainability and readability over cleverness.""",
        llm=llm,
        verbose=False,
    )

    readability_analyst = Agent(
        role="Code Readability Analyst",
        goal="Assess whether the code is self-documenting and easy to maintain",
        backstory="""You specialize in code comprehension and documentation.
You evaluate variable names, function length, complexity, and whether the code
communicates its intent clearly. You flag overly complex logic that should be simplified.""",
        llm=llm,
        verbose=False,
    )

    return Crew(
        agents=[style_reviewer, readability_analyst],
        tasks=[],  # Tasks added dynamically per review
        process=Process.sequential,
        verbose=False,
    )


def review_with_crew(diff: str, openai_api_key: str) -> str:
    """Create per-request crew tasks and run the review."""
    llm = LLM(model="gpt-4o", api_key=openai_api_key, temperature=0)

    style_reviewer = Agent(
        role="Senior Code Style Reviewer",
        goal="Identify style issues, naming violations, and readability problems in code diffs",
        backstory="""You are a meticulous code reviewer with 15 years of experience.
You enforce PEP 8 for Python, clean architecture principles, and clear naming conventions.""",
        llm=llm,
        verbose=False,
    )

    readability_analyst = Agent(
        role="Code Readability Analyst",
        goal="Assess whether the code is self-documenting and easy to maintain",
        backstory="You specialize in code comprehension and ensuring code communicates intent clearly.",
        llm=llm,
        verbose=False,
    )

    style_task = Task(
        description=f"""Review this code diff for style issues:

{diff}

Check for:
- PEP 8 violations (Python) or equivalent for other languages
- Inconsistent naming (camelCase vs snake_case mixing, unclear names)
- Lines too long (>120 chars)
- Missing or poor docstrings
- Magic numbers/strings that should be constants

Return a JSON object with findings.""",
        expected_output="""JSON object: {
  "findings": [{"line": "...", "issue": "...", "severity": "LOW|MEDIUM|HIGH", "suggestion": "..."}],
  "style_score": 0-10,
  "summary": "one-sentence summary"
}""",
        agent=style_reviewer,
    )

    readability_task = Task(
        description="""Based on the style review, assess the overall readability of the changes.
Focus on: function/variable naming clarity, cognitive complexity, and whether the code
is self-documenting. Produce a final merged JSON review.""",
        expected_output="""Final merged JSON: {
  "findings": [...combined findings...],
  "style_score": 0-10,
  "readability_score": 0-10,
  "summary": "combined summary"
}""",
        agent=readability_analyst,
        context=[style_task],
    )

    crew = Crew(
        agents=[style_reviewer, readability_analyst],
        tasks=[style_task, readability_task],
        process=Process.sequential,
        verbose=False,
    )

    result = crew.kickoff()
    return result.raw


# ── A2A Agent Executor ────────────────────────────────────────────────────────

class StyleAgentExecutor(AgentExecutor):
    def __init__(self, openai_api_key: str) -> None:
        self._api_key = openai_api_key

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

        logger.info("Style agent reviewing diff (%d chars)", len(diff_text))

        # CrewAI is sync — run in thread pool to avoid blocking event loop
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, review_with_crew, diff_text, self._api_key
        )

        event_queue.enqueue_event(new_agent_text_message(result))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError


# ── A2A Server Setup ──────────────────────────────────────────────────────────

def build_app(openai_api_key: str, port: int = 8011):
    agent_card = AgentCard(
        name="Style Review Agent",
        description="Reviews code diffs for style, naming conventions, readability, and maintainability using a CrewAI crew",
        url=f"http://localhost:{port}/",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="style_review",
                name="Code Style Review",
                description="Checks PEP 8 conformance, naming conventions, docstrings, line length, magic numbers",
                tags=["style", "readability", "pep8", "naming"],
                inputModes=["text/plain"],
                outputModes=["application/json"],
            )
        ],
    )

    handler = DefaultRequestHandler(
        agent_executor=StyleAgentExecutor(openai_api_key),
        task_store=InMemoryTaskStore(),
    )
    app_instance = A2AStarletteApplication(agent_card=agent_card, http_handler=handler)
    return app_instance.build()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.environ["OPENAI_API_KEY"]
    port = int(os.environ.get("STYLE_AGENT_PORT", "8011"))

    logging.basicConfig(level=logging.INFO)
    logger.info("Starting Style Review Agent on port %d", port)
    uvicorn.run(build_app(api_key, port), host="0.0.0.0", port=port)

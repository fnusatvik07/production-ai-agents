"""
swarm.py
~~~~~~~~
Assembles the competitive intelligence LangGraph Swarm.
Agents make local handoff decisions based on what they find.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph_swarm import create_handoff_tool, create_swarm
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger(__name__)

BROWSER_MCP_URL = os.environ.get("BROWSER_MCP_URL", "http://localhost:9100/mcp")


async def load_browser_tools() -> list:
    """Load browser MCP tools as LangChain tools."""
    try:
        async with streamablehttp_client(BROWSER_MCP_URL) as (r, w, _):
            async with ClientSession(r, w) as session:
                await session.initialize()
                tools = await load_mcp_tools(session)
                logger.info("Loaded %d browser tools", len(tools))
                return tools
    except Exception as e:
        logger.warning("Could not connect to browser MCP: %s. Agents will have no browser tools.", e)
        return []


def build_swarm(openai_api_key: str, browser_tools: list) -> Any:
    """Build the competitive intelligence swarm."""
    llm = ChatOpenAI(model="gpt-4o", api_key=openai_api_key, temperature=0)

    # ── Product Agent ──────────────────────────────────────────────────────────
    product_agent = create_react_agent(
        llm,
        tools=[
            *browser_tools,
            create_handoff_tool(
                agent_name="PricingAgent",
                description="Hand off to PricingAgent when you detect pricing page changes or new pricing tiers",
            ),
            create_handoff_tool(
                agent_name="SynthesisAgent",
                description="Hand off to SynthesisAgent when product analysis is complete and no pricing changes found",
            ),
        ],
        state_modifier="""You monitor competitor product pages for changes.

For each competitor URL:
1. Use navigate_and_extract to fetch the product/features page
2. Look for: new features, product name changes, beta announcements, changelogs
3. Note any pricing section changes you observe

If you find pricing changes → handoff to PricingAgent
If no significant changes → handoff to SynthesisAgent with your findings.

Always include the URL and specific changes found in your handoff message.""",
        name="ProductAgent",
    )

    # ── Pricing Agent ──────────────────────────────────────────────────────────
    pricing_agent = create_react_agent(
        llm,
        tools=[
            *browser_tools,
            create_handoff_tool(
                agent_name="HiringAgent",
                description="Hand off to HiringAgent when you detect enterprise tier introduction or significant price increases (signals enterprise expansion)",
            ),
            create_handoff_tool(
                agent_name="SynthesisAgent",
                description="Hand off to SynthesisAgent when pricing analysis is complete and no enterprise signals found",
            ),
        ],
        state_modifier="""You analyze competitor pricing pages.

Use extract_pricing_tiers to get structured pricing data.
Compare with what ProductAgent reported.

Key signals to flag:
- New enterprise/custom tier appearing
- Price increases >20%
- New per-seat pricing (signals enterprise expansion)
- Free tier removal (signals product maturation)

If enterprise signals detected → handoff to HiringAgent
Otherwise → handoff to SynthesisAgent with findings.""",
        name="PricingAgent",
    )

    # ── Hiring Agent ──────────────────────────────────────────────────────────
    hiring_agent = create_react_agent(
        llm,
        tools=[
            *browser_tools,
            create_handoff_tool(
                agent_name="PatentAgent",
                description="Hand off to PatentAgent when hiring shows AI/ML/infrastructure surge (may correlate with patent activity)",
            ),
            create_handoff_tool(
                agent_name="SynthesisAgent",
                description="Hand off to SynthesisAgent when hiring analysis is complete",
            ),
        ],
        state_modifier="""You analyze competitor job postings for strategic signals.

Use search_job_postings with these keyword groups:
- Enterprise: ["enterprise", "sales", "account executive", "CSM"]
- AI/ML: ["machine learning", "AI", "LLM", "data scientist"]
- Infrastructure: ["platform", "infrastructure", "SRE", "scalability"]

Hiring spikes in a domain indicate strategic investment.
If AI/ML hiring surge detected → handoff to PatentAgent
Otherwise → handoff to SynthesisAgent.""",
        name="HiringAgent",
    )

    # ── Patent Agent ──────────────────────────────────────────────────────────
    patent_agent = create_react_agent(
        llm,
        tools=[
            *browser_tools,
            create_handoff_tool(
                agent_name="SynthesisAgent",
                description="Hand off to SynthesisAgent when patent research is complete",
            ),
        ],
        state_modifier="""You research competitor patent activity.

Use search_patents with technology keywords relevant to the company's domain.
Look for: new AI/ML patents, infrastructure patents, security patents.

Relate patent findings to what previous agents discovered.
Always handoff to SynthesisAgent when done.""",
        name="PatentAgent",
    )

    # ── Synthesis Agent ────────────────────────────────────────────────────────
    synthesis_agent = create_react_agent(
        llm,
        tools=[],  # No tools — synthesis only
        state_modifier="""You synthesize all competitive intelligence findings into a structured brief.

Create a brief with:
## Executive Summary (2-3 sentences)
## Signal Chain (what each agent found, in order of discovery)
## Key Insights (3-5 bullet points)
## Risk Assessment (LOW/MEDIUM/HIGH with reasoning)
## Recommended Actions (specific, actionable)
## Metrics to Monitor

Be specific — cite actual findings, not generic observations.
End with: BRIEF_COMPLETE""",
        name="SynthesisAgent",
    )

    from langgraph.checkpoint.memory import InMemorySaver

    swarm = create_swarm(
        agents=[product_agent, pricing_agent, hiring_agent, patent_agent, synthesis_agent],
        default_active_agent="ProductAgent",
    )
    return swarm.compile(checkpointer=InMemorySaver())

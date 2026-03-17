"""
browser_mcp.py
~~~~~~~~~~~~~~
FastMCP server that exposes Playwright browser operations as MCP tools.
Used by all competitive intelligence agents for web scraping.

Run: uv run python -m src.mcp_browser.browser_mcp
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastmcp import FastMCP, Context

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "browser-mcp",
    dependencies=["playwright"],
    instructions="Browser automation tools for web scraping and competitive intelligence gathering.",
)


async def get_browser():
    """Get or create a Playwright browser instance."""
    from playwright.async_api import async_playwright
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    return browser, playwright


@mcp.tool
async def navigate_and_extract(
    url: str,
    css_selector: str = "body",
    wait_for: str | None = None,
    ctx: Context = None,
) -> str:
    """
    Navigate to a URL and extract text content matching a CSS selector.

    Args:
        url: URL to navigate to
        css_selector: CSS selector to extract (default: full body text)
        wait_for: Optional CSS selector to wait for before extracting

    Returns:
        Extracted text content
    """
    await ctx.info(f"Navigating to: {url}")

    browser, playwright = await get_browser()
    try:
        page = await browser.new_page()
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (compatible; CompetitiveIntelligenceBot/1.0)"
        })

        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        if wait_for:
            await page.wait_for_selector(wait_for, timeout=10000)

        elements = await page.query_selector_all(css_selector)
        texts = []
        for el in elements[:20]:  # cap at 20 elements
            text = await el.inner_text()
            if text.strip():
                texts.append(text.strip())

        return "\n\n".join(texts) if texts else "No content found"

    except Exception as e:
        logger.warning("Navigation failed for %s: %s", url, e)
        return f"Error navigating to {url}: {e}"
    finally:
        await browser.close()
        await playwright.stop()


@mcp.tool
async def extract_pricing_tiers(url: str, ctx: Context = None) -> dict:
    """
    Extract pricing information from a SaaS pricing page.
    Attempts to find tier names, prices, and features.

    Args:
        url: Pricing page URL

    Returns:
        Dict with tiers list: [{name, price, billing, features}]
    """
    await ctx.info(f"Extracting pricing from: {url}")

    # First get the raw text
    content = await navigate_and_extract(url, css_selector="main, .pricing, [class*='price'], [class*='plan']", ctx=ctx)

    # Use LLM to extract structured pricing
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from pydantic import BaseModel

    class PricingTier(BaseModel):
        name: str
        monthly_price: str | None
        annual_price: str | None
        billing_type: str
        features: list[str]
        is_enterprise: bool

    class PricingPage(BaseModel):
        tiers: list[PricingTier]
        currency: str
        has_free_tier: bool
        has_enterprise_tier: bool

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        api_key=os.environ.get("OPENAI_API_KEY"),
    ).with_structured_output(PricingPage)

    prompt = ChatPromptTemplate.from_messages([
        ("system", "Extract pricing tier information from this pricing page content."),
        ("human", "Pricing page content:\n{content}"),
    ])

    try:
        result = await (prompt | llm).ainvoke({"content": content[:3000]})
        return result.model_dump()
    except Exception as e:
        return {"tiers": [], "error": str(e), "raw_content": content[:500]}


@mcp.tool
async def search_job_postings(
    company_domain: str,
    keywords: list[str],
    days_back: int = 60,
    ctx: Context = None,
) -> dict:
    """
    Search for recent job postings at a company. Uses LinkedIn and Indeed.

    Args:
        company_domain: Company domain (e.g., "competitor.com")
        keywords: Job title keywords to search for
        days_back: How many days back to search

    Returns:
        {"total_found": N, "roles": [{title, posted_date, location, seniority}]}
    """
    await ctx.info(f"Searching job postings for {company_domain}")

    # In production: use LinkedIn API or Indeed scraping
    # For development: return mock data
    mock_roles = [
        {"title": f"Senior {kw} Engineer", "posted_date": "2026-03-10", "location": "Remote", "seniority": "senior"}
        for kw in keywords[:3]
    ]

    return {
        "company": company_domain,
        "search_keywords": keywords,
        "days_back": days_back,
        "total_found": len(mock_roles),
        "roles": mock_roles,
        "note": "Mock data in development — configure LinkedIn/Indeed credentials for live results",
    }


@mcp.tool
async def search_patents(
    assignee: str,
    keywords: list[str],
    filed_after: str = "2025-01-01",
    ctx: Context = None,
) -> dict:
    """
    Search USPTO for recent patents by a company.

    Args:
        assignee: Company name as patent assignee
        keywords: Technology keywords to search
        filed_after: ISO date — only return patents filed after this date

    Returns:
        {"patents": [{id, title, filed_date, abstract, url}]}
    """
    await ctx.info(f"Searching patents for {assignee}")

    # USPTO Patent Full-Text Search API (public)
    import httpx
    query = f'assignee:"{assignee}" AND ({" OR ".join(keywords)})'

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://efts.uspto.gov/LATEST/search-index",
                params={"q": query, "dateRangeField": "filing_date", "dateRange": f"{filed_after}:*", "hits.hits.total.value": "true"},
                timeout=15.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                hits = data.get("hits", {}).get("hits", [])
                patents = [
                    {
                        "id": h.get("_id", ""),
                        "title": h.get("_source", {}).get("patent_title", ""),
                        "filed_date": h.get("_source", {}).get("filing_date", ""),
                        "abstract": h.get("_source", {}).get("abstract_text", "")[:300],
                    }
                    for h in hits[:10]
                ]
                return {"assignee": assignee, "patents": patents, "total": len(patents)}
    except Exception as e:
        logger.warning("USPTO search failed: %s", e)

    return {
        "assignee": assignee,
        "patents": [],
        "note": "USPTO API unavailable — check connectivity",
    }


# ── Resources ─────────────────────────────────────────────────────────────────

@mcp.resource("browser://status")
async def browser_status() -> str:
    """Check if browser automation is available."""
    try:
        from playwright.async_api import async_playwright
        return json.dumps({"playwright": "available", "headless": True})
    except ImportError:
        return json.dumps({"playwright": "not_installed", "install": "playwright install chromium"})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("BROWSER_MCP_PORT", "9100"))
    logger.info("Starting Browser MCP server on port %d", port)
    mcp.run(transport="http", port=port)

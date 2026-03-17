"""
team.py
~~~~~~~
Assembles the AutoGen SelectorGroupChat financial intelligence team.
The selector LLM uses regime context to prioritize agent selection.
"""

from __future__ import annotations

import logging
import os
from typing import Sequence

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_agentchat.teams import SelectorGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient

from .regime_detector import RegimeAnalysis

logger = logging.getLogger(__name__)


# ── Tools per Agent ───────────────────────────────────────────────────────────

async def get_fred_series(series_id: str, limit: int = 10) -> dict:
    """Fetch economic data series from FRED (Federal Reserve Economic Data)."""
    import httpx
    api_key = os.environ.get("FRED_API_KEY", "demo_key")
    url = f"https://api.stlouisfed.org/fred/series/observations"
    params = {"series_id": series_id, "api_key": api_key, "file_type": "json",
               "sort_order": "desc", "limit": limit}
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "series_id": series_id,
                "observations": data.get("observations", [])[:limit],
            }
        return {"error": f"FRED API error: {resp.status_code}"}


async def get_stock_metrics(ticker: str) -> dict:
    """Get key financial metrics for a stock ticker."""
    import yfinance as yf
    stock = yf.Ticker(ticker)
    info = stock.info
    return {
        "ticker": ticker,
        "pe_ratio": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "price_to_book": info.get("priceToBook"),
        "revenue_growth": info.get("revenueGrowth"),
        "earnings_growth": info.get("earningsGrowth"),
        "debt_to_equity": info.get("debtToEquity"),
        "current_ratio": info.get("currentRatio"),
        "roe": info.get("returnOnEquity"),
        "profit_margin": info.get("profitMargins"),
    }


async def search_news_sentiment(query: str, days: int = 7) -> dict:
    """Search recent news and return sentiment summary."""
    # In production: use NewsAPI or similar
    # Mock response for development
    return {
        "query": query,
        "article_count": 42,
        "sentiment": {"positive": 0.45, "neutral": 0.35, "negative": 0.20},
        "top_headlines": [
            "Tech earnings beat expectations amid AI spending surge",
            "Fed signals cautious approach to rate cuts",
            "S&P 500 hits resistance at 5,200 level",
        ],
        "note": "Using mock data — configure NEWS_API_KEY for live results",
    }


async def calculate_risk_metrics(ticker: str, period: str = "1y") -> dict:
    """Calculate volatility, Sharpe ratio, max drawdown for a ticker."""
    import yfinance as yf
    import numpy as np

    stock = yf.Ticker(ticker)
    hist = stock.history(period=period)

    if hist.empty:
        return {"error": f"No data for {ticker}"}

    returns = hist["Close"].pct_change().dropna()

    volatility = float(returns.std() * (252 ** 0.5))  # annualized
    sharpe = float((returns.mean() * 252) / (returns.std() * (252 ** 0.5))) if returns.std() > 0 else 0.0

    # Max drawdown
    cumulative = (1 + returns).cumprod()
    rolling_max = cumulative.cummax()
    drawdown = (cumulative - rolling_max) / rolling_max
    max_drawdown = float(drawdown.min())

    # VaR 95%
    var_95 = float(np.percentile(returns, 5))

    return {
        "ticker": ticker,
        "annualized_volatility": round(volatility, 4),
        "sharpe_ratio": round(sharpe, 3),
        "max_drawdown": round(max_drawdown, 4),
        "var_95_daily": round(var_95, 4),
        "period": period,
        "data_points": len(returns),
    }


# ── Agent Assembly ────────────────────────────────────────────────────────────

def build_team(regime: RegimeAnalysis, openai_api_key: str) -> SelectorGroupChat:
    """Build the financial intelligence team with regime-aware selector."""

    model_client = OpenAIChatCompletionClient(
        model="gpt-4o",
        api_key=openai_api_key,
    )

    macro_agent = AssistantAgent(
        name="MacroAgent",
        model_client=model_client,
        tools=[get_fred_series],
        system_message="""You are a macroeconomist specializing in monetary policy, yield curves, and economic cycles.
Use get_fred_series to fetch economic data. Key series: GDP (GDP), Inflation (CPIAUCSL),
Fed Funds Rate (FEDFUNDS), Unemployment (UNRATE), 10Y Yield (DGS10).
Always contextualize data in the current macro environment. Be quantitative and cite specific data points.""",
    )

    earnings_agent = AssistantAgent(
        name="EarningsAgent",
        model_client=model_client,
        tools=[get_stock_metrics],
        system_message="""You are an equity analyst specializing in earnings quality and fundamental analysis.
Use get_stock_metrics to fetch financial metrics. Focus on:
- Earnings quality (accruals ratio, cash conversion)
- Valuation relative to growth (PEG ratio)
- Balance sheet strength (D/E, current ratio)
- Return metrics (ROE, margins)
Be skeptical — identify potential earnings manipulation signals.""",
    )

    sentiment_agent = AssistantAgent(
        name="SentimentAgent",
        model_client=model_client,
        tools=[search_news_sentiment],
        system_message="""You are a market sentiment analyst. Use search_news_sentiment to analyze news.
Identify: narrative shifts, sector rotation signals, crowding risk, and contrarian opportunities.
Distinguish between sentiment-driven price moves and fundamental-driven ones.""",
    )

    risk_agent = AssistantAgent(
        name="RiskAgent",
        model_client=model_client,
        tools=[calculate_risk_metrics],
        system_message="""You are a quantitative risk analyst. Use calculate_risk_metrics to compute risk metrics.
Focus on: tail risk (VaR, CVaR), correlation breaks, drawdown patterns, and volatility regime changes.
Translate quantitative risk metrics into actionable position sizing guidance.""",
    )

    synthesis_agent = AssistantAgent(
        name="SynthesisAgent",
        model_client=model_client,
        system_message="""You are the chief investment strategist. Synthesize inputs from all specialist agents.
Produce a structured investment thesis with:
1. Key findings from each specialist
2. Opportunities and risks (weighted by regime)
3. Specific actionable recommendations
4. Key metrics to monitor
5. Confidence level and dissenting views

End your response with "ANALYSIS_COMPLETE" when done.""",
    )

    # Build regime-aware selector prompt
    agent_list = ", ".join(regime.agent_priority)
    selector_prompt = f"""You are selecting the next specialist agent to speak.

Current market regime: {regime.regime.value} (confidence: {regime.confidence:.0%})
{regime.context_prompt}

Preferred agent order for this regime: {agent_list}

RULES:
- Select the agent whose expertise is most needed given what's been said so far
- Don't call the same agent twice unless new information requires it
- Once all needed specialists have contributed, select SynthesisAgent to conclude
- Never select an agent who just spoke

Agents: {{agentlist}}
History: {{history}}

Select next agent:"""

    termination = TextMentionTermination("ANALYSIS_COMPLETE") | MaxMessageTermination(20)

    return SelectorGroupChat(
        participants=[macro_agent, earnings_agent, sentiment_agent, risk_agent, synthesis_agent],
        model_client=model_client,
        selector_prompt=selector_prompt,
        termination_condition=termination,
    )

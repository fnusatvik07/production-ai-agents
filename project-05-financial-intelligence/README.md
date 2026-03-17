# Project 05 · Multi-Agent Financial Intelligence System

> AutoGen SelectorGroupChat with regime-aware agent routing, Arize Phoenix observability, and WebSocket streaming

---

## Overview

A financial research platform where an LLM-powered **selector** dynamically routes each question to the most appropriate specialist based on the full conversation context. A **market regime detector** pre-classifies market conditions (risk-on/off/trending/range-bound) and biases agent selection accordingly. All agent interactions are traced end-to-end in **Arize Phoenix** for full observability.

---

## Architecture

```mermaid
flowchart TB
    UQ([User Question]) --> RD

    subgraph PRE["Pre-Processing"]
        RD[Regime Detector\nVIX + yield curve + momentum]
    end

    RD -->|regime label + agent_priority| SGC

    subgraph SGC["AutoGen SelectorGroupChat"]
        direction TB
        SEL[Selector LLM\nreads full conversation history]
        SEL -->|picks next speaker| MA
        SEL -->|picks next speaker| EA
        SEL -->|picks next speaker| SA
        SEL -->|picks next speaker| RA
        SEL -->|picks next speaker| SYN

        MA[MacroAgent\nFRED + World Bank]
        EA[EarningsAgent\nSEC EDGAR]
        SA[SentimentAgent\nNews + Social]
        RA[RiskAgent\nyfinance + VaR]
        SYN[SynthesisAgent\nInvestment Thesis]
    end

    SYN -->|ANALYSIS_COMPLETE| OUT([Investment Brief])

    subgraph OBS["Observability"]
        PHX[Arize Phoenix :6006\nOTel-native traces]
    end

    SGC --> OBS
    OUT --> WS[FastAPI WebSocket\nStreaming to client]

    style PRE fill:#fff3e0,stroke:#FF9800
    style SGC fill:#e8f4fd,stroke:#2196F3
    style OBS fill:#e8fde8,stroke:#4CAF50
```

![Architecture](./diagram.png)

---

## Flow

1. **Regime detection** — fetches VIX (`^VIX`), SPY SMA20/SMA50 momentum, 10Y-2Y yield spread via yfinance; classifies into 4 regimes
2. **Regime-aware selector prompt** — agent priority list injected into `SelectorGroupChat` system prompt
3. **SelectorGroupChat** — on each turn, selector LLM reads full conversation history and decides which specialist to activate next
4. **Specialist agents** call their tools (FRED API, SEC EDGAR, NewsAPI, yfinance) and return findings as messages
5. **SynthesisAgent** integrates all findings into a structured investment thesis, then emits `ANALYSIS_COMPLETE`
6. **Termination** — `TextMentionTermination("ANALYSIS_COMPLETE") | MaxMessageTermination(20)`
7. **Phoenix traces** every LLM call, tool call, and agent transition with OpenTelemetry

---

## Key Concepts

| Concept | Description |
|---------|-------------|
| **SelectorGroupChat** | LLM reads full history to decide who speaks next — more accurate than round-robin |
| **Regime Detection** | VIX + yield curve + momentum → 4-class regime → biased agent priority |
| **TextMentionTermination** | Conversation stops when any agent outputs the termination string |
| **Phoenix/Arize** | Self-hosted OTel-native observability for multi-agent systems |
| **WebSocket Streaming** | Token-by-token agent output streamed to frontend in real-time |
| **Agent Tool Isolation** | Each agent has access only to its domain's tools — no cross-contamination |

---

## Stack

| Layer | Library | Version |
|-------|---------|---------|
| Multi-Agent | AutoGen AgentChat | ≥ 0.4.0 |
| LLM | OpenAI GPT-4o | — |
| Observability | Arize Phoenix | ≥ 4.0.0 |
| Market Data | yfinance | ≥ 0.2.40 |
| Economic Data | fredapi | ≥ 0.5.0 |
| API | FastAPI + WebSocket | ≥ 0.115.0 |
| Persistence | asyncpg (PostgreSQL) | ≥ 0.29.0 |

---

## Project Structure

```
project-05-financial-intelligence/
├── .env.example
├── docker-compose.yml          # Phoenix self-hosted
├── pyproject.toml
└── src/
    ├── __init__.py
    ├── agents/
    │   ├── __init__.py
    │   ├── macro_agent.py       # FRED API + World Bank tools
    │   ├── earnings_agent.py    # SEC EDGAR + earnings metrics
    │   ├── sentiment_agent.py   # NewsAPI + Reddit sentiment
    │   ├── risk_agent.py        # yfinance: Sharpe, VaR, drawdown
    │   └── synthesis_agent.py   # Final investment thesis
    ├── regime_detector.py       # VIX + yield curve → regime classification
    ├── team.py                  # SelectorGroupChat assembly + termination
    ├── observability.py         # Phoenix register() + OTel instrumentation
    └── api.py                   # FastAPI: /analyze (blocking) + /analyze/ws (stream)
```

---

## Quick Start

```bash
cd project-05-financial-intelligence
uv sync
cp .env.example .env
# Fill: OPENAI_API_KEY, FRED_API_KEY, NEWS_API_KEY (optional)

# Start Phoenix observability (self-hosted)
docker compose up -d phoenix

# Start the API
uv run uvicorn src.api:app --port 8005

# Blocking query
curl -X POST http://localhost:8005/analyze \
  -H "Content-Type: application/json" \
  -d '{"question": "Is current earnings quality sustainable for large-cap tech?"}'

# View traces at http://localhost:6006
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | GPT-4o for all agents | required |
| `FRED_API_KEY` | FRED economic data | required |
| `NEWS_API_KEY` | NewsAPI for sentiment | optional |
| `PHOENIX_PORT` | Phoenix UI port | `6006` |
| `POSTGRES_URI` | Conversation persistence | `postgresql://fin:fin@localhost:5432/fin` |
| `MAX_AGENT_TURNS` | Max messages before forced termination | `20` |

---

## Market Regime Detection

```python
# Regime signals and resulting agent priority:
#
# RISK_OFF  — VIX > 25, yield curve inverted
#   agent_priority: [RiskAgent, MacroAgent, EarningsAgent, SentimentAgent, SynthesisAgent]
#
# RISK_ON   — VIX < 15, curve normal, SPY above both SMAs
#   agent_priority: [EarningsAgent, SentimentAgent, MacroAgent, RiskAgent, SynthesisAgent]
#
# TRENDING  — SPY strongly above SMA50
#   agent_priority: [SentimentAgent, RiskAgent, EarningsAgent, MacroAgent, SynthesisAgent]
#
# RANGE_BOUND — Low VIX, mixed momentum
#   agent_priority: [MacroAgent, EarningsAgent, RiskAgent, SentimentAgent, SynthesisAgent]
```

---

## Phoenix Observability

Phoenix captures the full agent conversation as nested OTel spans:

```
Session: analyze-query-abc123
  ├── Span: regime_detection            150ms
  ├── Span: MacroAgent — get_fred       320ms
  ├── Span: SelectorGroupChat.select    210ms
  ├── Span: EarningsAgent — sec_edgar  1.2s
  ├── Span: SelectorGroupChat.select    190ms
  └── Span: SynthesisAgent — generate  890ms
```

View at `http://localhost:6006` — filter by session, agent name, tool, or latency threshold.

---

## Latency Profile

| Operation | Typical |
|-----------|---------|
| Regime detection | ~150ms |
| MacroAgent (FRED) | ~320ms |
| EarningsAgent (SEC) | ~1.2s |
| SentimentAgent (news) | ~800ms |
| SynthesisAgent | ~900ms |
| **Total (4–5 agent turns)** | **~4–6s** |

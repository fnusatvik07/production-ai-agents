# Project 08 · PR Lifecycle Agent

> LangGraph + Claude SDK agent with ADR-aware code review, parallel analysis via Send API, confidence-gated HITL, and DeepEval CI/CD evaluation

---

## Overview

An autonomous PR review agent that understands your codebase's **Architecture Decision Records** and applies them during code review. Unlike generic linters, this agent reads ADRs from `docs/decisions/` into a Chroma knowledge base and flags violations (e.g., *"ADR-007: All DB access must use Repository pattern — this PR violates it at auth/service.py:42"*).

Three analysis workers run **in parallel** via LangGraph's `Send` API. Comments are gated by confidence: high-confidence findings post automatically; low-confidence findings pause with `interrupt()` for senior engineer review before posting.

---

## Architecture

```mermaid
flowchart TB
    GH([GitHub PR Opened / Synchronized]) --> API

    subgraph API["FastAPI :8008"]
        WH[/webhook/github]
        WH --> VERIFY[Verify HMAC signature]
        VERIFY --> AG
    end

    subgraph AG["LangGraph StateGraph"]
        direction TB
        FP[fetch_pr_content]
        SA[search_relevant_adrs]
        DA[dispatch_analysis_workers\nSend API fan-out]
        SC[score_comments]
        HG{human_review_gate}
        PC[post_comments]
        UL[update_pr_labels]

        FP --> SA --> DA --> SC --> HG
        HG -->|confidence ≥ 0.85| PC
        HG -->|confidence < 0.85| INT["interrupt()"]
        INT --> ENG([Senior Engineer Review])
        ENG -->|approve / edit / reject| CMD["Command(resume=...)"]
        CMD --> PC
        PC --> UL
    end

    SA <-->|semantic search| ADR[(Chroma\nADR Knowledge Base)]

    subgraph WORKERS["Parallel Workers (Send API)"]
        direction LR
        WSec[analyze_security]
        WArch[analyze_architecture\n← ADR context]
        WTest[analyze_test_coverage]
    end

    DA --> WORKERS
    WORKERS -->|findings| SC

    UL --> GHAPI[(GitHub API\nInline Comments + Labels)]

    subgraph EVAL["DeepEval CI"]
        GE[GEval Correctness]
        HM[HallucinationMetric]
        FM[FaithfulnessMetric]
    end

    style AG fill:#e8f4fd,stroke:#2196F3
    style WORKERS fill:#fff3e0,stroke:#FF9800
    style ADR fill:#f3e8fd,stroke:#9C27B0
    style EVAL fill:#e8fde8,stroke:#4CAF50
```

![Architecture](./diagram.png)

---

## Flow

1. **GitHub webhook** fires on PR open/sync → HMAC signature verified
2. **`fetch_pr_content`** — fetches diff, file list, PR metadata via GitHub API
3. **`search_relevant_adrs`** — semantic search over ADR Chroma KB using PR diff as query
4. **`dispatch_analysis_workers`** — emits `[Send("analyze_security", ...), Send("analyze_architecture", ...), Send("analyze_tests", ...)]` — all three run in parallel
5. **`score_comments`** — LLM assigns confidence (0–1) to each finding
6. **`human_review_gate`** — high confidence → auto-post; low confidence → `interrupt()` for engineer review
7. **`post_comments`** — inline GitHub review comments at file:line positions
8. **`update_pr_labels`** — applies labels (`needs-security-review`, `adr-violation`, etc.)

---

## Key Concepts

| Concept | Description |
|---------|-------------|
| **ADR-Aware Review** | Chroma KB of architectural decisions; violations cited with article + line |
| **`Send` API** | Parallel worker dispatch — security, architecture, test analysis run concurrently |
| **Confidence-Gated HITL** | Only `interrupt()` when comment confidence < threshold (not always) |
| **Inline PR Comments** | Comments posted at specific `file:line` positions via GitHub API |
| **DeepEval CI** | `GEval`, `HallucinationMetric`, `FaithfulnessMetric` on golden dataset in CI |
| **ADR Parsing** | Regex-based extraction of title, status, decision section from Markdown |

---

## Stack

| Layer | Library | Version |
|-------|---------|---------|
| Agent Framework | LangGraph | ≥ 0.4.0 |
| LLM | Claude Sonnet 4.6 | — |
| Evaluation | DeepEval | ≥ 1.0.0 |
| ADR Store | Chroma | ≥ 0.6.0 |
| GitHub | FastMCP + PyGithub | — |
| API | FastAPI + uvicorn | ≥ 0.115.0 |
| Embeddings | OpenAI text-embedding-3-small | — |

---

## Project Structure

```
project-08-pr-lifecycle-agent/
├── .env.example
├── docker-compose.yml
├── pyproject.toml
├── docs/
│   └── decisions/            # Your ADR files go here (*.md)
├── .github/
│   └── workflows/
│       └── evaluate-pr-agent.yml
└── src/
    ├── __init__.py
    ├── adr_store.py           # ADR parser + Chroma ingest + semantic search
    ├── github_mcp.py          # FastMCP server wrapping GitHub REST API
    ├── analysis/
    │   ├── __init__.py
    │   ├── security.py        # OWASP, injection, secrets
    │   ├── architecture.py    # ADR violation detection
    │   └── test_coverage.py   # Coverage gaps, missing edge cases
    ├── agent.py               # LangGraph StateGraph (Send + interrupt)
    ├── evaluation.py          # DeepEval CI runner
    └── api.py                 # FastAPI: /webhook/github
```

---

## Quick Start

```bash
cd project-08-pr-lifecycle-agent
uv sync
cp .env.example .env
# Fill: ANTHROPIC_API_KEY, OPENAI_API_KEY, GITHUB_TOKEN, GITHUB_WEBHOOK_SECRET

docker compose up -d

# Ingest your ADRs
uv run python -m src.adr_store --ingest ./docs/decisions/

# Start GitHub MCP server
uv run python -m src.github_mcp &   # port 9080

# Start PR agent API
uv run uvicorn src.api:app --port 8008

# Configure GitHub webhook:
# URL: https://your-server:8008/webhook/github
# Events: pull_request (opened, synchronize, reopened)
# Secret: your GITHUB_WEBHOOK_SECRET value
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Claude API key | required |
| `OPENAI_API_KEY` | Embeddings | required |
| `GITHUB_TOKEN` | Post inline comments + labels | required |
| `GITHUB_WEBHOOK_SECRET` | Validate webhook HMAC | required |
| `CONFIDENCE_THRESHOLD` | Below this → HITL interrupt | `0.85` |
| `CHROMA_HOST` | ADR KB host | `localhost` |
| `CHROMA_PORT` | ADR KB port | `8000` |

---

## ADR Format

Place ADRs in `docs/decisions/*.md`:

```markdown
# ADR-007: Use Repository Pattern for All Database Access

## Status: Accepted

## Context
Direct database queries scattered across services make testing difficult.

## Decision
All database operations MUST go through a Repository class.
Direct use of SQLAlchemy sessions in service classes is prohibited.

## Consequences
- Positive: Easier to mock, clear boundaries
- Negative: More boilerplate for simple queries
```

The agent flags any PR that adds `db.session.query(...)` directly in a service file as an ADR-007 violation, citing the exact file and line.

---

## DeepEval CI Pipeline

```yaml
# .github/workflows/evaluate-pr-agent.yml
- name: Evaluate PR Agent Quality
  run: |
    uv run python -m src.evaluation \
      --golden-dataset tests/golden_pr_reviews.json \
      --fail-below 0.80
```

Metrics evaluated:
- **G-Eval correctness** — did it catch the same issues as an expert reviewer?
- **HallucinationMetric** — does it cite issues that don't exist in the diff?
- **FaithfulnessMetric** — are ADR citations accurate to the source document?

---

## Latency Profile

| Operation | Typical |
|-----------|---------|
| GitHub diff fetch | ~200ms |
| ADR semantic search | ~80ms |
| Parallel analysis workers (3x) | ~2.0s |
| Comment scoring | ~400ms |
| GitHub comment POST | ~300ms |
| **Total (auto-post path)** | **~3.0s** |

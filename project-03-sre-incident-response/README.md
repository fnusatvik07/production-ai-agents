# Project 03 · SRE Incident Response Agent

> LangGraph HITL agent that executes runbooks via FastMCP tool servers, pauses at dangerous steps for human approval, and auto-generates postmortems — with PostgreSQL-backed durable state

---

## Overview

An on-call SRE agent that ingests alerts (PagerDuty/AlertManager), retrieves the matching runbook from a semantic knowledge base, and executes remediation steps through FastMCP tool servers (kubectl, AWS CLI, HTTP health checks). When it reaches a **dangerous operation** (pod deletion, database restart), it `interrupt()`s — surfacing the pending action to the on-call engineer via REST. After human approval/edit/rejection, it resumes exactly where it paused.

The defining production challenge: **durable execution across process crashes**. The PostgreSQL checkpointer saves state after every node, so a mid-runbook crash is transparent to the recovery flow.

---

## Architecture

```mermaid
flowchart TB
    AL([Alert: PagerDuty / AlertManager]) --> API

    subgraph API["FastAPI :8003"]
        direction TB
        ALRT[POST /alert]
        APR[POST /approve/thread_id]
        ALRT --> LG
        APR -->|Command resume| LG
    end

    subgraph LG["LangGraph StateGraph"]
        direction TB
        TR[triage_alert]
        RR[retrieve_runbook]
        PE[plan_execution]
        ES[execute_step]
        EV[evaluate_result]
        PM[write_postmortem]

        TR --> RR --> PE --> ES --> EV
        EV -->|next step| ES
        EV -->|resolved| PM
        EV -->|dangerous| HITL
        HITL -->|approved| ES
        HITL -->|rejected| EV
    end

    subgraph HITL["Human-in-the-Loop"]
        direction TB
        INT["interrupt()"]
        ENG([On-call Engineer])
        INT --> ENG
    end

    RR -->|semantic search| CHR[(Chroma\nRunbook KB)]

    subgraph MCP["FastMCP Tool Servers"]
        direction TB
        KM[kubectl-mcp :9010]
        AM[aws-mcp :9011]
        HM[http-check-mcp :9012]
    end

    ES --> MCP
    LG -->|checkpoint| PG[(PostgreSQL\nCheckpointer)]

    style LG fill:#e8f4fd,stroke:#2196F3
    style HITL fill:#fff3e0,stroke:#FF9800
    style MCP fill:#f3e8fd,stroke:#9C27B0
    style API fill:#e8fde8,stroke:#4CAF50
```

![Architecture](./diagram.png)

---

## Flow

1. **Alert arrives** → `triage_alert` classifies severity and extracts service name
2. **Runbook retrieval** → semantic search over Chroma KB returns the most relevant procedure
3. **Plan execution** → LLM decomposes runbook into ordered steps with risk classifications
4. **Step loop** — for each step:
   - Call the appropriate MCP tool (kubectl, AWS CLI, or HTTP check)
   - `evaluate_result` checks success/failure
   - If step is `dangerous: true` → `interrupt()` pauses graph, returns pending action to human
5. **Human decision** → approve / edit command / reject via `POST /approve/{thread_id}`
6. **Postmortem** → auto-generated Markdown with full timeline when incident resolves

---

## Key Concepts

| Concept | Description |
|---------|-------------|
| **`interrupt()`** | Pauses graph mid-execution, surfaces state to human — no polling needed |
| **`Command(resume=...)`** | Resumes graph from interrupt with human decision attached |
| **AsyncPostgresSaver** | Checkpoint every node — survives process restarts |
| **FastMCP Tool Servers** | Isolated processes exposing kubectl/AWS/HTTP as MCP tools |
| **langchain-mcp-adapters** | `load_mcp_tools()` converts MCP tools to LangChain tool objects |
| **Dry-run mode** | `KUBECTL_DRY_RUN=true` — all kubectl calls echo instead of execute |
| **Runbook RAG** | Chroma-backed semantic search over Markdown runbook files |

---

## Stack

| Layer | Library | Version |
|-------|---------|---------|
| Agent Framework | LangGraph | ≥ 0.4.0 |
| Checkpointer | langgraph-checkpoint-postgres | ≥ 0.4.0 |
| Tool Protocol | FastMCP | ≥ 3.0.0 |
| MCP Adapter | langchain-mcp-adapters | ≥ 0.2.0 |
| LLM | Claude Sonnet 4.6 | — |
| Runbook Store | Chroma | ≥ 0.6.0 |
| API | FastAPI + uvicorn | ≥ 0.115.0 |
| Database | PostgreSQL (asyncpg) | 16 |

---

## Project Structure

```
project-03-sre-incident-response/
├── .env.example
├── docker-compose.yml
├── pyproject.toml
├── runbooks/
│   ├── high_memory_usage.md
│   ├── database_connection_pool.md
│   └── api_latency_spike.md
└── src/
    ├── __init__.py
    ├── mcp_servers/
    │   ├── __init__.py
    │   ├── kubectl_mcp.py        # FastMCP: kubectl get/describe/logs/delete/rollout
    │   ├── aws_mcp.py            # FastMCP: ECS restart, RDS reboot, CloudWatch
    │   └── http_check_mcp.py    # FastMCP: endpoint health + latency checks
    ├── runbook_store.py          # Chroma ingest + semantic search
    ├── agent.py                  # LangGraph StateGraph with HITL loop
    └── api.py                   # FastAPI: /alert, /approve, /incident
```

---

## Quick Start

```bash
cd project-03-sre-incident-response
uv sync
cp .env.example .env
# Fill: ANTHROPIC_API_KEY, POSTGRES_URI (or use docker-compose default)

# Start infrastructure
docker compose up -d

# Ingest runbooks into Chroma
uv run python -m src.runbook_store --ingest runbooks/

# Start MCP tool servers
uv run python -m src.mcp_servers.kubectl_mcp &    # :9010
uv run python -m src.mcp_servers.aws_mcp &        # :9011
uv run python -m src.mcp_servers.http_check_mcp & # :9012

# Start the SRE agent API
uv run uvicorn src.api:app --port 8003

# Simulate a critical alert
curl -X POST http://localhost:8003/alert \
  -H "Content-Type: application/json" \
  -d '{
    "alert_name": "HighMemoryUsage",
    "service": "api-gateway",
    "severity": "critical",
    "labels": {"pod": "api-gateway-7f8b9d-xk2p", "namespace": "production"}
  }'
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Claude API key | required |
| `POSTGRES_URI` | Checkpoint storage | `postgresql://sre:sre@localhost:5432/sre` |
| `CHROMA_HOST` | Runbook KB host | `localhost` |
| `CHROMA_PORT` | Runbook KB port | `8000` |
| `KUBECTL_DRY_RUN` | Safe mode (echo only) | `false` |
| `KUBECTL_MCP_URL` | kubectl MCP server | `http://localhost:9010` |
| `AWS_MCP_URL` | AWS CLI MCP server | `http://localhost:9011` |
| `HTTP_CHECK_MCP_URL` | HTTP check MCP server | `http://localhost:9012` |
| `DANGER_THRESHOLD` | Min risk score for HITL pause | `0.7` |

---

## Human-in-the-Loop

When the agent hits a dangerous step, it pauses and the API returns:

```json
{
  "status": "awaiting_approval",
  "thread_id": "incident-abc123",
  "pending_action": {
    "tool": "kubectl",
    "command": "kubectl delete pod api-gateway-7f8b9d-xk2p -n production",
    "rationale": "Pod stuck in CrashLoopBackOff — restart triggers fresh deploy",
    "risk_score": 0.85
  }
}
```

Resume options:

```bash
# Approve as-is
curl -X POST http://localhost:8003/approve/incident-abc123 \
  -H "Content-Type: application/json" \
  -d '{"decision": "approve"}'

# Edit then approve
curl -X POST http://localhost:8003/approve/incident-abc123 \
  -H "Content-Type: application/json" \
  -d '{"decision": "edit", "edited_command": "kubectl rollout restart deploy/api-gateway -n production"}'

# Reject (agent skips step and continues)
curl -X POST http://localhost:8003/approve/incident-abc123 \
  -H "Content-Type: application/json" \
  -d '{"decision": "reject"}'
```

---

## Durable Execution

The PostgreSQL checkpointer saves state after every node. If the process crashes mid-runbook, just restart — the agent resumes from the last saved step:

```bash
# Process died at step 4 of 7
# Restart:
uv run uvicorn src.api:app --port 8003

# Check incident state — shows exactly where it left off
curl http://localhost:8003/incident/incident-abc123
```

---

## Sample Postmortem

```markdown
# Postmortem: HighMemoryUsage — api-gateway (2026-03-17)

## Timeline
- 14:23 Alert triggered (memory: 94%)
- 14:24 Runbook retrieved: high_memory_usage.md
- 14:25 HTTP /health → 200 OK (service still responding)
- 14:26 kubectl top pods: api-gateway 3.8Gi / 4Gi limit
- 14:27 ⏸  Human approval requested: delete pod
- 14:28 ✅ Approved by on-call
- 14:28 kubectl delete pod api-gateway-7f8b9d-xk2p
- 14:30 Memory stabilized at 58%

## Root Cause
Memory leak in GraphQL subscription cleanup — connections not released.

## Action Items
- [ ] Fix subscription handler connection pool cleanup
- [ ] Lower memory alert threshold: 90% → 80%
```

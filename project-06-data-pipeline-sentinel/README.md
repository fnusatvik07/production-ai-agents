# Project 06 · Agentic Data Pipeline Sentinel

> LangGraph agent with episodic memory that learns from past schema drift, monitors Kafka/S3 pipelines, and auto-generates Great Expectations rules

---

## Overview

A data quality guardian that monitors streaming pipelines (Kafka topics, S3 events) for schema drift and statistical anomalies. Unlike rule-based monitors, this agent **learns from its own history** — using LangGraph's `Store` with pgvector semantic search to recall past incidents. After 30+ days it builds institutional knowledge about which data sources tend to drift, what seasonal patterns look like, and which anomalies are genuine vs. expected.

---

## Architecture

```mermaid
flowchart TB
    KF([Kafka Topics]) --> KM
    S3([S3 Event Notifications]) --> SM

    subgraph MONITOR["Data Monitors"]
        KM[kafka_monitor.py\nbatch buffering]
        SM[s3_monitor.py\nevent handler]
    end

    KM --> AGENT
    SM --> AGENT

    subgraph AGENT["LangGraph StateGraph"]
        direction TB
        DA[detect_anomalies\nstatistical + schema diff]
        RH[recall_history\nsemantic memory search]
        CS[classify_severity\nLOW / MEDIUM / HIGH]
        ACT[take_actions]

        DA --> RH --> CS --> ACT
    end

    RH <-->|pgvector search| MEM[(LangGraph Store\nPostgreSQL + pgvector)]

    subgraph ACTIONS["Actions by Severity"]
        direction TB
        LOW[LOW: auto-update\nGX expectations]
        MED[MEDIUM: GX update\n+ GitHub issue]
        HIGH[HIGH: GX update\n+ GitHub issue\n+ page oncall\n+ trigger DAG rerun]
    end

    ACT --> LOW
    ACT --> MED
    ACT --> HIGH

    AGENT -->|store every event| MEM
    HIGH --> GH[(GitHub Issues)]
    HIGH --> AF[Airflow / Prefect\nDAG trigger]
    ACT --> GX[Great Expectations\nExpectation Suite]

    style AGENT fill:#e8f4fd,stroke:#2196F3
    style MONITOR fill:#fff3e0,stroke:#FF9800
    style ACTIONS fill:#f3e8fd,stroke:#9C27B0
    style MEM fill:#e8fde8,stroke:#4CAF50
```

![Architecture](./diagram.png)

---

## Flow

1. **Monitor** receives a data batch → extracts schema and sample statistics
2. **`detect_anomalies`** — schema diff (new/removed columns, type changes) + statistical drift (null rate, mean shift z-score, variance change)
3. **`recall_history`** — semantic search over past incidents: *"What happened when orders_topic got a new column last time?"*
4. **`classify_severity`** — LLM weighs detected changes against historical context: same pattern → LOW; novel + breaking → HIGH
5. **`take_actions`** — triggers are tiered by severity (see above)
6. **`store_memory`** — every event stored to pgvector for future recall (agent always learns)

---

## Key Concepts

| Concept | Description |
|---------|-------------|
| **LangGraph Store** | Cross-session semantic memory; namespace per data source |
| **Episodic Memory** | Past incidents retrieved by semantic similarity to current anomaly |
| **Schema Diffing** | New columns, removed columns, breaking type changes detected structurally |
| **Statistical Drift** | Null rate delta, mean z-score, variance ratio, range violations |
| **Great Expectations** | Auto-generated expectation suites with bounds from observed distributions |
| **Event-Driven Agent** | Agent triggered by pipeline events, not user queries |

---

## Stack

| Layer | Library | Version |
|-------|---------|---------|
| Agent Framework | LangGraph + Store | ≥ 0.4.0 |
| Memory Store | PostgreSQL + pgvector | 16 |
| LLM | Claude Sonnet 4.6 | — |
| Data Validation | Great Expectations | ≥ 1.0.0 |
| Stream Consumer | kafka-python | ≥ 2.0.0 |
| Statistical Analysis | pandas + scipy | — |
| GitHub Integration | PyGithub | ≥ 2.3.0 |
| API | FastAPI + uvicorn | ≥ 0.115.0 |

---

## Project Structure

```
project-06-data-pipeline-sentinel/
├── .env.example
├── docker-compose.yml          # Kafka · PostgreSQL + pgvector · Zookeeper
├── pyproject.toml
└── src/
    ├── __init__.py
    ├── monitors/
    │   ├── __init__.py
    │   ├── kafka_monitor.py      # Consumer + batch buffering
    │   └── s3_monitor.py         # S3 event notification handler
    ├── analysis/
    │   ├── __init__.py
    │   ├── schema_diff.py        # Structural schema comparison
    │   └── statistical.py        # Null rate, z-score, range checks
    ├── memory.py                 # SentinelMemory: store/recall/update_outcome
    ├── expectations.py           # GX expectation suite generation
    ├── agent.py                  # LangGraph StateGraph with episodic memory
    └── api.py                    # FastAPI: /check, /status, /memory/{source}
```

---

## Quick Start

```bash
cd project-06-data-pipeline-sentinel
uv sync
cp .env.example .env
# Fill: ANTHROPIC_API_KEY, POSTGRES_URI, KAFKA_BOOTSTRAP_SERVERS, GITHUB_TOKEN

docker compose up -d

# Start Kafka monitor
uv run python -m src.monitors.kafka_monitor &

# Start the API
uv run uvicorn src.api:app --port 8006

# Manually trigger a check (bypasses Kafka)
curl -X POST http://localhost:8006/check \
  -H "Content-Type: application/json" \
  -d '{"source": "orders_topic", "sample_size": 1000}'

# View memory for a source
curl http://localhost:8006/memory/orders_topic
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Claude API key | required |
| `POSTGRES_URI` | Memory + checkpoint DB | `postgresql://sentinel:sentinel@localhost:5432/sentinel` |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka brokers | `localhost:9092` |
| `KAFKA_TOPICS` | Comma-separated topics | `orders,payments,events` |
| `KAFKA_CONSUMER_GROUP` | Consumer group ID | `sentinel-group` |
| `AWS_ACCESS_KEY_ID` | S3 monitor | optional |
| `S3_MONITORED_BUCKET` | S3 bucket for event notifications | optional |
| `GITHUB_TOKEN` | File issues | optional |
| `GITHUB_REPO` | `owner/repo` for issues | optional |
| `NULL_RATE_CHANGE_THRESHOLD` | Delta before anomaly | `0.05` |
| `MEAN_CHANGE_THRESHOLD_STDS` | Z-score threshold | `3.0` |
| `CHECK_INTERVAL_SECONDS` | Batch check frequency | `300` |

---

## Episodic Memory

The agent stores a structured record for every drift event:

```python
{
  "source": "orders_topic",
  "event_type": "schema_drift",
  "timestamp": "2026-03-17T14:23:00Z",
  "changes": ["new column: discount_pct", "type change: amount str→float"],
  "severity": "MEDIUM",
  "resolution": "auto-updated expectations, filed issue #234",
  "outcome": "downstream pipelines unaffected",
}
```

On the next drift event for the same source, the agent recalls similar past incidents:

```python
memories = await store.search(
    namespace=("sentinel", "orders_topic"),
    query="schema drift column added",
    limit=5,
)
# Agent sees: "Last time orders_topic had a new column (3 months ago),
# discount_pct was null for 2 days before being populated.
# Resolution: wait 48h before updating downstream transforms."
```

---

## Great Expectations Auto-Generation

When schema changes are detected, the sentinel auto-generates updated expectation suites:

```python
# Before drift:
expect_column_to_exist("amount")
expect_column_values_to_be_of_type("amount", "float")

# After sentinel detects new column with observed distribution:
expect_column_to_exist("discount_pct")
expect_column_values_to_be_between("discount_pct", min_value=0.0, max_value=1.0, mostly=0.95)
# Bounds inferred from observed percentiles (p5 / p95)
```

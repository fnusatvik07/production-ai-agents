# Project 09 · Adaptive Learning Agent

> LangGraph + LangMem tutoring system with per-student long-term semantic memory, SM-2 spaced repetition scheduling, and scaffolded hint interrupts

---

## Overview

An intelligent tutoring agent that **remembers each student across sessions**. Unlike a stateless chatbot, this agent maintains per-student semantic memory of misconceptions, mastery levels, and learning pace. It schedules concept reviews using the **SM-2 spaced repetition algorithm** and scaffolds hints using `interrupt()` — generating one hint at a time, pausing for the student's attempt, then deciding whether to reveal more.

After several sessions, the agent knows: *"Alice struggles with recursion base cases, prefers visual explanations, and has binary search due for review today."*

---

## Architecture

```mermaid
flowchart TB
    ST([Student Question via WebSocket]) --> SUP

    subgraph SUP["LangGraph Supervisor"]
        direction TB
        CT[classify_topic]
        RC[recall_student_context]
        CDR[check_due_reviews]
        RTE[route_to_expert]
        SH[scaffolded_hints\nHITL interrupt loop]
        USR[update_spaced_repetition]
        SSM[store_session_memory]

        CT --> RC --> CDR --> RTE --> SH --> USR --> SSM
    end

    RC <-->|pgvector semantic search| MEM[(LangGraph Store\nPostgreSQL + pgvector)]
    SSM --> MEM

    subgraph EXPERTS["Subject Expert Agents"]
        direction LR
        MA[MathAgent\nalgebra/calculus/stats]
        CA[CodeAgent\nPython/algorithms]
        SCA[ScienceAgent\nphysics/chemistry/bio]
    end

    RTE --> EXPERTS

    subgraph HITL["Scaffolded Hints (HITL)"]
        direction TB
        H1["interrupt() → hint 1"]
        ATT1[Student attempt]
        H2["interrupt() → hint 2"]
        ATT2[Student attempt]
        H3["interrupt() → full answer"]
        H1 --> ATT1 --> H2 --> ATT2 --> H3
    end

    SH --> HITL
    HITL -->|quality score 0-5| SM2[SM-2 Algorithm\nupdate ease_factor + interval]
    SM2 --> USR

    style SUP fill:#e8f4fd,stroke:#2196F3
    style EXPERTS fill:#fff3e0,stroke:#FF9800
    style HITL fill:#f3e8fd,stroke:#9C27B0
    style MEM fill:#e8fde8,stroke:#4CAF50
```

![Architecture](./diagram.png)

---

## Flow

1. **Student sends question** via WebSocket (`ws://localhost:8009/tutor/{student_id}`)
2. **`classify_topic`** — routes to math, code, or science agent
3. **`recall_student_context`** — semantic search over student's memory namespace: past struggles, mastery levels, learning style
4. **`check_due_reviews`** — SM-2 scheduler checks for overdue concepts; proactively brings them up
5. **Expert agent** generates a response tailored to the student's profile
6. **Scaffolded hint loop** — `interrupt()` after each hint; evaluates student attempt; continues or reveals more
7. **SM-2 update** — quality score (0–5) based on hint usage → updates `ease_factor`, `interval_days`, `next_review_date`
8. **`store_session_memory`** — session insights persisted to pgvector for future recall

---

## Key Concepts

| Concept | Description |
|---------|-------------|
| **LangGraph Store** | Namespace-isolated semantic memory per student: `("student", student_id)` |
| **SM-2 Algorithm** | Standard spaced repetition: ease factor × interval → optimal review date |
| **Scaffolded HITL** | Multi-turn interrupt loop — reveal hints progressively, not all at once |
| **Mastery Tracking** | Per-concept mastery score (0–1) persisted and updated after each session |
| **Supervisor Pattern** | Central graph routes to subject-expert sub-agents |
| **LangMem** | `create_manage_memory_tool` and `create_search_memory_tool` for agent memory access |
| **WebSocket Streaming** | Token-by-token tutor output streamed in real-time |

---

## Stack

| Layer | Library | Version |
|-------|---------|---------|
| Agent Framework | LangGraph + Store | ≥ 0.4.0 |
| Memory | LangMem | ≥ 0.1.0 |
| Memory Store | PostgreSQL + pgvector | 16 |
| LLM | Claude Sonnet 4.6 | — |
| API | FastAPI + WebSocket | ≥ 0.115.0 |
| Embeddings | OpenAI text-embedding-3-small | — |

---

## Project Structure

```
project-09-adaptive-learning-agent/
├── .env.example
├── docker-compose.yml          # PostgreSQL + pgvector
├── pyproject.toml
└── src/
    ├── __init__.py
    ├── agents/
    │   ├── __init__.py
    │   ├── math_agent.py        # Algebra, calculus, statistics tutor
    │   ├── code_agent.py        # Python, algorithms, data structures tutor
    │   └── science_agent.py     # Physics, chemistry, biology tutor
    ├── memory/
    │   ├── __init__.py
    │   ├── student_store.py     # Student profile + concept mastery CRUD
    │   └── spaced_repetition.py # SM-2 algorithm implementation
    ├── supervisor.py            # LangGraph StateGraph with routing
    └── api.py                   # FastAPI + WebSocket server
```

---

## Quick Start

```bash
cd project-09-adaptive-learning-agent
uv sync
cp .env.example .env
# Fill: ANTHROPIC_API_KEY, OPENAI_API_KEY, POSTGRES_URI

docker compose up -d

uv run uvicorn src.api:app --port 8009

# Connect via WebSocket (any WebSocket client)
# ws://localhost:8009/tutor/alice_123
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Claude API key | required |
| `OPENAI_API_KEY` | Embeddings | required |
| `POSTGRES_URI` | Student memory store | `postgresql://tutor:tutor@localhost:5432/tutor` |
| `MAX_HINTS` | Max hints before revealing answer | `3` |
| `CONFIDENCE_THRESHOLD` | SM-2 quality → mastery mapping boundary | `0.6` |

---

## SM-2 Spaced Repetition

After each student interaction, mastery and review schedule are updated:

```python
# Quality scores:
# 5 — Perfect recall on first attempt
# 3 — Recalled with effort (needed 1-2 hints)
# 1 — Failed to recall (needed full answer)
# 0 — Complete blackout

def update_card(card: ConceptCard, quality: int) -> ConceptCard:
    new_ease = card.ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ease = max(1.3, new_ease)   # Floor at 1.3

    if quality < 3:
        repetition, interval = 0, 1         # Start over
    elif card.repetition == 0:
        interval = 1
    elif card.repetition == 1:
        interval = 6
    else:
        interval = round(card.interval_days * new_ease)

    return ConceptCard(
        concept=card.concept,
        ease_factor=new_ease,
        interval_days=interval,
        repetition=card.repetition + 1,
        next_review_date=date.today() + timedelta(days=interval),
    )
```

---

## Student Memory Example

After 3 sessions, a student's namespace contains:

```
Namespace: ("student", "alice_123")

"Consistently struggles with recursion base cases — 4 failed attempts over 3 sessions"
"Strong with list comprehensions — mastery: 0.92, ease: 2.8, next review in 22 days"
"Prefers visual analogies and step-by-step breakdowns"
"Review due: binary_search (overdue 2 days), dynamic_programming (due tomorrow)"
"Completed: sorting algorithms (mastery: 0.87), big-O notation (mastery: 0.79)"
```

---

## WebSocket Protocol

```jsonc
// Student sends:
{ "question": "I'm stuck on recursion" }

// Agent responds with first hint (interrupt):
{ "type": "hint", "index": 1, "content": "What should happen when the input is the smallest possible value?" }

// Student responds with attempt:
{ "attempt": "If n is 0, return 0?" }

// Agent evaluates and gives feedback:
{ "type": "feedback", "correct": true, "explanation": "Exactly — that's the base case. Now think about the recursive step..." }

// After session ends:
{ "type": "mastery_update", "concept": "recursion", "quality": 3, "new_mastery": 0.65, "next_review": "2026-03-20" }
```

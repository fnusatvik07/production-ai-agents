export const projects = [
  {
    id: "01",
    title: "GraphRAG Research Engine",
    tagline: "Graph-augmented RAG that reasons across 50k+ documents",
    description:
      "Combines Neo4j knowledge graphs with semantic vector search. Multi-hop reasoning retrieves facts from connected entities rather than flat document chunks.",
    tech: ["LangGraph 0.4", "Neo4j", "Claude 3.5 Sonnet", "RAGAS", "FastAPI"],
    category: "RAG & Knowledge Graphs",
    gradient: "from-blue-900 via-blue-800 to-indigo-900",
    accent: "#3b82f6",
    mermaid: `flowchart TB
    subgraph Input["Input Layer"]
        Q[User Query]
        QE[Query Embedding\\ncl100k_base]
    end
    subgraph Retrieval["Dual Retrieval"]
        VS[Vector Search\\npgvector top-k]
        GQ[Cypher Query\\nNeo4j multi-hop]
    end
    subgraph Fusion["Context Fusion"]
        RR[Reciprocal Rank\\nFusion]
        CTX[Context Window\\n≤ 128k tokens]
    end
    subgraph Generation["Generation"]
        LLM[Claude 3.5 Sonnet]
        EVAL[RAGAS Evaluator\\nfaithfulness · recall]
    end
    Q --> QE --> VS & GQ --> RR --> CTX --> LLM --> EVAL
    style Input fill:#1e3a5f,color:#fff
    style Retrieval fill:#1e3a5f,color:#fff
    style Fusion fill:#2d1b69,color:#fff
    style Generation fill:#1a3d2b,color:#fff`,
    keyCode: `# src/agent.py — Multi-hop graph retrieval
from langgraph.graph import StateGraph, START
from langchain_anthropic import ChatAnthropic

async def retrieve_graph(state: ResearchState) -> ResearchState:
    """Multi-hop retrieval: vector + Cypher fusion"""
    vector_hits = await vectorstore.asimilarity_search(
        state["query"], k=10
    )
    cypher = """
    MATCH (e:Entity)-[:RELATED_TO*1..3]-(neighbor)
    WHERE e.name IN $entities
    RETURN neighbor.text, neighbor.source
    LIMIT 20
    """
    graph_hits = await neo4j.arun(cypher, entities=state["entities"])

    # Reciprocal Rank Fusion
    state["context"] = rrf_merge(vector_hits, graph_hits)
    return state`,
    tutorial: [
      "Clone the repo and `cd project-01-graphrag-research-engine`",
      "Copy `.env.example` → `.env`, set `ANTHROPIC_API_KEY` and `NEO4J_URI`",
      "Run `docker compose up -d` to start Neo4j + PostgreSQL",
      "Ingest documents: `python scripts/ingest.py --source ./data/papers/`",
      "Start the API: `uvicorn src.api:app --reload`",
      "POST to `/research` with `{\"query\": \"What are the latest LLM safety techniques?\"}`",
      "View RAGAS eval scores in the response — faithfulness, recall, precision",
    ],
    overview: {
      problem:
        "Traditional RAG systems retrieve flat document chunks, losing the relational structure between concepts. When answering complex research questions, you need to traverse entity relationships across thousands of documents.",
      whoUsesIt: "Research teams, knowledge management platforms, enterprise search systems",
      whyItMatters:
        "Multi-hop graph traversal enables answering questions like 'What are the second-order effects of X on Y?' that flat vector search cannot handle. RAGAS evaluation ensures answer quality is measurable.",
    },
  },
  {
    id: "02",
    title: "A2A Code Review Network",
    tagline: "Three specialized agents review code in parallel via A2A protocol",
    description:
      "LangGraph, CrewAI, and raw Anthropic SDK agents each review different aspects (security, architecture, tests) and post a unified GitHub comment.",
    tech: ["A2A SDK v0.3", "LangGraph 0.4", "CrewAI", "GitHub API", "FastAPI"],
    category: "Multi-Agent Networks",
    gradient: "from-orange-900 via-red-900 to-rose-900",
    accent: "#f97316",
    mermaid: `flowchart TB
    GH[GitHub Webhook\\nPR opened / updated]
    ORCH[Orchestrator Agent\\nLangGraph]
    SA[Security Agent\\nLangGraph]
    AA[Architecture Agent\\nCrewAI]
    TA[Test Coverage Agent\\nAnthropic SDK]
    AGG[Aggregator\\nSynthesis + Score]
    COMMENT[GitHub PR Comment\\nUnified Report]
    GH --> ORCH
    ORCH -->|A2A task| SA & AA & TA
    SA & AA & TA -->|A2A result| AGG --> COMMENT
    style ORCH fill:#7c2d12,color:#fff
    style SA fill:#1e3a5f,color:#fff
    style AA fill:#2d1b69,color:#fff
    style TA fill:#1a3d2b,color:#fff`,
    keyCode: `# src/orchestrator.py — Fan-out via A2A
from a2a.client import A2AClient

async def fan_out_review(pr_diff: str) -> list[ReviewResult]:
    agents = [
        A2AClient("http://security-agent:8001"),
        A2AClient("http://arch-agent:8002"),
        A2AClient("http://test-agent:8003"),
    ]
    tasks = [
        agent.send_task({"diff": pr_diff, "role": role})
        for agent, role in zip(agents, ["security", "architecture", "tests"])
    ]
    results = await asyncio.gather(*tasks)
    return [r.result for r in results]`,
    tutorial: [
      "Set up GitHub webhook pointing to `http://your-host:8000/webhook`",
      "Start all agents: `docker compose up`",
      "Open a PR in your test repo",
      "Watch the orchestrator fan out tasks to all 3 agents via A2A",
      "See the unified review comment appear on your PR in ~2 seconds",
    ],
    overview: {
      problem:
        "Code review is multidimensional — security vulnerabilities, architectural drift, and test coverage gaps require different expertise. A single reviewer (human or AI) rarely catches all three simultaneously.",
      whoUsesIt: "Engineering teams, open-source maintainers, DevSecOps pipelines",
      whyItMatters:
        "A2A protocol enables heterogeneous agents (LangGraph + CrewAI + raw SDK) to collaborate without shared infrastructure. Each agent runs independently and results are synthesized into a single actionable report.",
    },
  },
  {
    id: "03",
    title: "SRE Incident Response",
    tagline: "AI-assisted incident triage with human approval gates",
    description:
      "LangGraph HITL loop: detects anomaly → retrieves runbook → plans remediation steps → pauses for human approval before executing each step.",
    tech: ["LangGraph 0.4", "FastMCP", "PostgreSQL", "PagerDuty", "Prometheus"],
    category: "Human-in-the-Loop Systems",
    gradient: "from-red-900 via-rose-900 to-pink-900",
    accent: "#ef4444",
    mermaid: `flowchart TB
    ALERT[PagerDuty Alert\\n/ Prometheus Rule]
    TRIAGE[triage_incident\\nclassify severity]
    RUNBOOK[retrieve_runbook\\npgvector search]
    PLAN[plan_remediation\\nstep list]
    INTERRUPT[interrupt\\nHuman Approval]
    EXEC[execute_step\\nFastMCP tools]
    POST[postmortem\\nmarkdown report]
    ALERT --> TRIAGE --> RUNBOOK --> PLAN --> INTERRUPT
    INTERRUPT -->|approved| EXEC --> INTERRUPT
    INTERRUPT -->|all done| POST
    style INTERRUPT fill:#7f1d1d,color:#fff,stroke:#ef4444
    style TRIAGE fill:#1e3a5f,color:#fff
    style EXEC fill:#1a3d2b,color:#fff`,
    keyCode: `# src/agent.py — HITL interrupt pattern
from langgraph.types import interrupt, Command

def execute_step(state: IncidentState):
    step = state["plan"][state["step_idx"]]

    # Pause and ask human
    decision = interrupt({
        "action": step["action"],
        "risk": step["risk_level"],
        "rollback": step["rollback_cmd"],
    })

    if decision["approve"]:
        result = mcp_client.call_tool(step["tool"], step["args"])
        return {"results": state["results"] + [result],
                "step_idx": state["step_idx"] + 1}
    return {"aborted": True}`,
    tutorial: [
      "Start services: `docker compose up -d`",
      "Trigger a test alert: `python scripts/fire_alert.py --type high_latency`",
      "Watch the agent triage and retrieve matching runbook",
      "Approve/reject remediation steps via `POST /resume` with `{\"approve\": true}`",
      "View generated postmortem at `/reports/latest`",
    ],
    overview: {
      problem:
        "Automated remediation is risky without oversight. Pure automation can make incidents worse; pure manual response is too slow at 3 AM. You need AI speed with human judgment at critical decision points.",
      whoUsesIt: "SRE teams, platform engineering, on-call engineers",
      whyItMatters:
        "LangGraph's interrupt() primitive pauses execution at arbitrary points, waiting for human input. This enables full auditability: every action taken has a human approval record with timestamp and approver.",
    },
  },
  {
    id: "04",
    title: "FastMCP Enterprise Gateway",
    tagline: "Single MCP gateway composing 8 tool servers with caching and tracing",
    description:
      "FastMCP 3.0 gateway mounts SQL, S3, Wiki, Jira servers. Redis cache reduces tool latency by 70%. OpenTelemetry traces every agent call.",
    tech: ["FastMCP 3.0", "Redis", "OpenTelemetry", "PostgreSQL", "S3"],
    category: "Protocol Layer (MCP & A2A)",
    gradient: "from-purple-900 via-violet-900 to-purple-800",
    accent: "#a855f7",
    mermaid: `flowchart TB
    AGENT[AI Agent]
    subgraph GW["FastMCP Gateway :8000"]
        RL[Rate Limiter\\n100 req/min]
        RC[Redis Cache\\nTTL 300s]
        TR[OTel Tracer]
    end
    SQL[SQL Server\\n/sql/*]
    S3[S3 Server\\n/s3/*]
    WIKI[Wiki Server\\n/wiki/*]
    JIRA[Jira Server\\n/jira/*]
    AGENT --> RL --> RC --> TR
    TR --> SQL & S3 & WIKI & JIRA
    style GW fill:#2d1b69,color:#fff`,
    keyCode: `# src/gateway.py — FastMCP server composition
from fastmcp import FastMCP
from fastmcp.contrib.cache import cached

gateway = FastMCP("Enterprise Gateway")

# Mount sub-servers
gateway.mount("/sql",  sql_server)
gateway.mount("/s3",   s3_server)
gateway.mount("/wiki", wiki_server)
gateway.mount("/jira", jira_server)

@gateway.tool()
@cached(ttl=300)
async def query_database(sql: str) -> dict:
    """Execute read-only SQL with result caching"""
    return await sql_server.execute(sql)`,
    tutorial: [
      "Set env vars for all downstream services in `.env`",
      "`docker compose up -d redis postgres`",
      "`uvicorn src.gateway:gateway --port 8000`",
      "Connect your agent with `mcp_url = 'http://localhost:8000'`",
      "Call `list_tools()` — you'll see all 8 sub-server tools merged",
      "Check OTel traces at `http://localhost:16686` (Jaeger)",
    ],
    overview: {
      problem:
        "Each AI agent integration needs its own tool wiring. As tool servers multiply (SQL, S3, Jira, Wiki...), you end up with N×M connection management and zero observability.",
      whoUsesIt: "Platform engineers building agent infrastructure, AI teams with multiple tool backends",
      whyItMatters:
        "A single MCP gateway with Redis caching eliminates redundant tool calls and provides unified rate limiting. OTel tracing gives you a complete flamegraph of every agent tool call chain.",
    },
  },
  {
    id: "05",
    title: "Financial Intelligence Platform",
    tagline: "Multi-agent market analysis with regime-aware agent selection",
    description:
      "AutoGen SelectorGroupChat routes queries to specialist agents (technical, fundamental, sentiment, macro, risk) based on detected market regime.",
    tech: ["AutoGen 0.4", "Claude 3.5 Sonnet", "Phoenix", "yfinance", "PostgreSQL"],
    category: "Multi-Agent Networks",
    gradient: "from-green-900 via-emerald-900 to-teal-900",
    accent: "#22c55e",
    mermaid: `flowchart TB
    RD[Regime Detector\\ntrend/volatile/ranging]
    SGC[SelectorGroupChat\\nAutoGen]
    TA[Technical\\nAgent]
    FA[Fundamental\\nAgent]
    SA[Sentiment\\nAgent]
    MA[Macro\\nAgent]
    RA[Risk\\nAgent]
    SYNTH[Synthesis Agent\\nfinal report]
    RD --> SGC
    SGC -->|selects| TA & FA & SA & MA & RA
    TA & FA & SA & MA & RA --> SYNTH
    style SGC fill:#14532d,color:#fff
    style SYNTH fill:#1e3a5f,color:#fff`,
    keyCode: `# src/agents.py — SelectorGroupChat
from autogen import SelectorGroupChat, AssistantAgent

agents = [technical_agent, fundamental_agent,
          sentiment_agent, macro_agent, risk_agent]

chat = SelectorGroupChat(
    agents=agents,
    model_client=claude_client,
    selector_prompt="""Select the next agent based on market regime: {regime}.
    Current speaker: {last_speaker}. Available: {agent_names}."""
)
result = await chat.run(task=f"Analyze {ticker} for regime: {regime}")`,
    tutorial: [
      "Set `ANTHROPIC_API_KEY` and optionally `PHOENIX_API_KEY`",
      "`uvicorn src.api:app --reload`",
      "POST to `/analyze`: `{\"ticker\": \"AAPL\", \"horizon\": \"1W\"}`",
      "Watch regime detection select which agents run",
      "View Phoenix traces at `http://localhost:6006`",
    ],
    overview: {
      problem:
        "Financial markets operate differently across regimes — a trending market needs technical analysis; a volatile market needs risk management; a ranging market needs mean-reversion strategies. One-size-fits-all agents miss this.",
      whoUsesIt: "Quant teams, fintech companies, portfolio managers",
      whyItMatters:
        "SelectorGroupChat dynamically picks which agents speak next based on context. This produces higher-quality analysis than static pipelines because the right expert is engaged for the current market conditions.",
    },
  },
  {
    id: "06",
    title: "Data Pipeline Sentinel",
    tagline: "Episodic memory agent that learns pipeline failure patterns",
    description:
      "Monitors Kafka/S3 pipelines, detects anomalies, recalls similar past failures from pgvector episodic memory, classifies severity and auto-remediates.",
    tech: ["LangGraph Store", "pgvector", "Kafka", "S3", "PostgreSQL"],
    category: "Memory & Monitoring",
    gradient: "from-cyan-900 via-teal-900 to-cyan-800",
    accent: "#06b6d4",
    mermaid: `flowchart TB
    SRC[Kafka / S3\\ndata sources]
    DET[detect_anomalies\\nstatistical + ML]
    MEM[recall_history\\npgvector similarity]
    SEV[classify_severity\\nLOW / MED / HIGH]
    LOW[Log & Monitor]
    MED[Slack Alert\\n+ auto-fix]
    HIGH[PagerDuty\\n+ human escalation]
    SRC --> DET --> MEM --> SEV
    SEV -->|LOW| LOW
    SEV -->|MEDIUM| MED
    SEV -->|HIGH| HIGH
    style DET fill:#1e3a5f,color:#fff
    style MEM fill:#2d1b69,color:#fff
    style HIGH fill:#7f1d1d,color:#fff`,
    keyCode: `# src/agent.py — Episodic memory recall
from langgraph.store.memory import InMemoryStore

async def recall_history(state: SentinelState, store: BaseStore):
    # Search past incidents by embedding similarity
    similar = await store.asearch(
        ("incidents", state["pipeline_id"]),
        query=state["anomaly_description"],
        limit=5,
    )
    state["similar_incidents"] = [s.value for s in similar]
    return state`,
    tutorial: [
      "Start dependencies: `docker compose up -d kafka postgres`",
      "Seed episodic memory: `python scripts/seed_history.py`",
      "Start sentinel: `python src/main.py`",
      "Simulate failure: `python scripts/inject_anomaly.py --type schema_drift`",
      "Watch it recall similar past incidents and classify severity",
    ],
    overview: {
      problem:
        "Data pipelines fail in recurring patterns — the same schema drift, same upstream delay, same volume spike. Without memory, an agent treats every incident as novel and can't apply institutional knowledge.",
      whoUsesIt: "Data engineering teams, platform teams, data reliability engineers",
      whyItMatters:
        "pgvector episodic memory means the agent gets smarter over time. After 100 incidents, it recognizes patterns humans haven't documented and auto-remediates with high confidence.",
    },
  },
  {
    id: "07",
    title: "Cross-Cloud Compliance",
    tagline: "GDPR, SOX and HIPAA audits across GCP, AWS, Azure simultaneously",
    description:
      "Orchestrator dispatches A2A tasks to cloud-specific agents in parallel. Each agent scans its cloud and returns compliance findings. Results merged into unified report.",
    tech: ["A2A SDK v0.3", "AWS Bedrock", "Google Vertex", "Azure OpenAI", "FastAPI"],
    category: "Protocol Layer (MCP & A2A)",
    gradient: "from-sky-900 via-blue-900 to-indigo-900",
    accent: "#0ea5e9",
    mermaid: `flowchart TB
    ORCH[Compliance Orchestrator\\nA2A + LangGraph]
    GCP[GDPR Agent\\nGoogle Cloud / Vertex]
    AWS[SOX Agent\\nAWS / Bedrock]
    AZ[HIPAA Agent\\nAzure / OpenAI]
    RPT[Unified Report\\nRisk + Remediation]
    ORCH -->|A2A task| GCP & AWS & AZ
    GCP & AWS & AZ -->|A2A result| RPT
    style ORCH fill:#1e3a5f,color:#fff
    style GCP fill:#14532d,color:#fff
    style AWS fill:#7c2d12,color:#fff
    style AZ fill:#2d1b69,color:#fff`,
    keyCode: `# src/orchestrator.py — Multi-cloud A2A dispatch
async def run_compliance_audit(scope: AuditScope):
    clients = {
        "gdpr": A2AClient("http://gcp-agent:8001"),
        "sox":  A2AClient("http://aws-agent:8002"),
        "hipaa":A2AClient("http://az-agent:8003"),
    }
    tasks = {
        framework: client.send_task({"scope": scope, "framework": framework})
        for framework, client in clients.items()
    }
    results = await asyncio.gather(*tasks.values())
    return merge_compliance_report(dict(zip(tasks.keys(), results)))`,
    tutorial: [
      "Configure cloud credentials in `.env` for all three clouds",
      "`docker compose up`",
      "POST to `/audit`: `{\"org\": \"acme\", \"frameworks\": [\"gdpr\",\"sox\",\"hipaa\"]}`",
      "Agents scan in parallel — typical time: 45–90 seconds",
      "Download unified report from `/report/{audit_id}`",
    ],
    overview: {
      problem:
        "Enterprise compliance spans multiple clouds, each with different APIs, different compliance frameworks, and different remediation paths. Manual audits take weeks and miss cross-cloud misconfigurations.",
      whoUsesIt: "Compliance teams, InfoSec, cloud architects at regulated enterprises",
      whyItMatters:
        "A2A enables cloud-native agents (each running on its own cloud with native credentials) to collaborate without centralising sensitive credentials. Parallel execution reduces audit time from weeks to minutes.",
    },
  },
  {
    id: "08",
    title: "PR Lifecycle Agent",
    tagline: "Automated PR reviews with confidence gates and HITL escalation",
    description:
      "LangGraph Send API fans out to 3 parallel reviewers (security, architecture, tests). Low-confidence reviews escalate to human; high-confidence auto-post.",
    tech: ["Anthropic SDK", "LangGraph Send", "DeepEval", "GitHub API", "FastAPI"],
    category: "Human-in-the-Loop Systems",
    gradient: "from-violet-900 via-purple-900 to-fuchsia-900",
    accent: "#8b5cf6",
    mermaid: `flowchart TB
    GH[GitHub Webhook]
    FETCH[fetch_pr\\ndiff + context]
    ADR[search_adrs\\npgvector]
    subgraph PAR["Parallel Review (Send API)"]
        SEC[Security\\nReviewer]
        ARCH[Architecture\\nReviewer]
        TEST[Test Coverage\\nReviewer]
    end
    GATE[confidence_gate\\n≥ 0.8 → auto-post]
    HITL[interrupt\\nHuman Review]
    POST[post_comment\\nGitHub API]
    GH --> FETCH --> ADR --> PAR
    PAR --> GATE
    GATE -->|high conf| POST
    GATE -->|low conf| HITL --> POST
    style PAR fill:#2d1b69,color:#fff
    style HITL fill:#7f1d1d,color:#fff`,
    keyCode: `# src/agent.py — Parallel review with Send API
from langgraph.types import Send

def route_reviews(state: PRState) -> list[Send]:
    """Fan out to specialized reviewers in parallel"""
    return [
        Send("security_review",     {**state, "focus": "security"}),
        Send("architecture_review", {**state, "focus": "architecture"}),
        Send("test_review",         {**state, "focus": "tests"}),
    ]

def confidence_gate(state: PRState):
    avg = sum(r["confidence"] for r in state["reviews"]) / 3
    if avg >= 0.8:
        return "post_comment"
    return "human_review"  # interrupt`,
    tutorial: [
      "Set up GitHub App or webhook with `GITHUB_TOKEN`",
      "`docker compose up`",
      "Open a PR — webhook fires automatically",
      "If confidence < 0.8, approve via `POST /resume`",
      "Check DeepEval scores: `pytest tests/eval/` for review quality metrics",
    ],
    overview: {
      problem:
        "AI code review can be confidently wrong. Without a quality gate, low-confidence reviews get posted and erode developer trust. You need automation that knows when to ask for help.",
      whoUsesIt: "Engineering teams with high PR volume, platform teams, open-source maintainers",
      whyItMatters:
        "DeepEval measures review quality on real test cases, and the confidence gate routes uncertain reviews to humans. This self-calibrating system improves over time as human feedback updates the confidence threshold.",
    },
  },
  {
    id: "09",
    title: "Adaptive Learning Agent",
    tagline: "Personalised tutoring with spaced repetition and scaffolded hints",
    description:
      "WebSocket-based tutoring agent with pgvector memory. Uses SM-2 algorithm to schedule reviews, provides progressive hints (never direct answers), tracks mastery per concept.",
    tech: ["LangMem", "pgvector", "SM-2 Algorithm", "WebSocket", "FastAPI"],
    category: "Human-in-the-Loop Systems",
    gradient: "from-amber-900 via-orange-900 to-yellow-900",
    accent: "#f59e0b",
    mermaid: `flowchart TB
    WS[WebSocket\\nstudent message]
    SUP[Supervisor\\nroute intent]
    MEM[recall_context\\npgvector memory]
    EXP[Expert Agent\\nconcept explanation]
    HINT[Hint Generator\\nscaffolded 1→2→3]
    SM2[SM-2 Update\\nease · interval · rep]
    STORE[store_memory\\nmastery score]
    WS --> SUP --> MEM --> EXP --> HINT
    HINT -->|after session| SM2 --> STORE
    style MEM fill:#2d1b69,color:#fff
    style SM2 fill:#7c2d12,color:#fff`,
    keyCode: `# src/agent.py — SM-2 spaced repetition
def update_sm2(card: FlashCard, quality: int) -> FlashCard:
    """quality: 0-5 (0=blackout, 5=perfect)"""
    if quality >= 3:
        if card.repetition == 0:
            card.interval = 1
        elif card.repetition == 1:
            card.interval = 6
        else:
            card.interval = round(card.interval * card.ease_factor)
        card.repetition += 1
        card.ease_factor = max(
            1.3,
            card.ease_factor + 0.1 - (5 - quality) * 0.08
        )
    else:
        card.repetition = 0
        card.interval = 1
    card.next_review = date.today() + timedelta(days=card.interval)
    return card`,
    tutorial: [
      "Start backend: `uvicorn src.api:app --reload`",
      "Connect via WebSocket: `wscat -c ws://localhost:8000/ws/student123`",
      "Send: `{\"message\": \"explain gradient descent\"}`",
      "Get progressive hints — agent never gives direct answers",
      "After session, SM-2 schedules your next review automatically",
    ],
    overview: {
      problem:
        "Generic AI tutors give direct answers, which short-circuit learning. And without memory, every session starts from scratch — the agent doesn't know what you studied yesterday or where you struggled.",
      whoUsesIt: "EdTech platforms, self-directed learners, coding bootcamps",
      whyItMatters:
        "SM-2 has 40 years of research behind it — it's the algorithm behind Anki. Combining it with LLM-generated scaffolded hints produces a tutor that's both pedagogically sound and personalised to each learner's pace.",
    },
  },
  {
    id: "10",
    title: "Competitive Intelligence Swarm",
    tagline: "Decentralized agent swarm tracking competitors across 5 dimensions",
    description:
      "LangGraph Swarm where agents handoff to each other: Product→Pricing→Hiring→Patent→Synthesis. Each agent uses FastMCP browser tools to scrape and analyze in real time.",
    tech: ["LangGraph Swarm", "FastMCP Browser", "Claude 3.5 Sonnet", "PostgreSQL"],
    category: "Multi-Agent Networks",
    gradient: "from-rose-900 via-pink-900 to-fuchsia-900",
    accent: "#ec4899",
    mermaid: `flowchart LR
    PROD[Product\\nAgent]
    PRICE[Pricing\\nAgent]
    HIRE[Hiring\\nAgent]
    PAT[Patent\\nAgent]
    SYNTH[Synthesis\\nAgent]
    PROD -->|handoff| PRICE
    PRICE -->|handoff| HIRE
    HIRE -->|handoff| PAT
    PAT -->|handoff| SYNTH
    style PROD fill:#7c2d12,color:#fff
    style SYNTH fill:#1e3a5f,color:#fff`,
    keyCode: `# src/agents.py — LangGraph Swarm
from langgraph_swarm import create_swarm, create_handoff_tool

product_agent = create_react_agent(
    model, tools=[
        scrape_product_page,
        create_handoff_tool(agent_name="pricing_agent")
    ],
    name="product_agent",
)
# ... define all agents similarly

swarm = create_swarm(
    [product_agent, pricing_agent, hiring_agent, patent_agent, synthesis_agent],
    default_active_agent="product_agent"
)`,
    tutorial: [
      "Start: `uvicorn src.api:app --reload`",
      "POST to `/analyze`: `{\"competitor\": \"openai.com\"}`",
      "Watch swarm handoff chain: product → pricing → hiring → patents",
      "Receive unified intelligence brief with all 5 dimensions",
      "Schedule recurring: `POST /schedule` with cron expression",
    ],
    overview: {
      problem:
        "Competitive intelligence requires tracking product changes, pricing, hiring signals, patents and partnerships simultaneously. Manual monitoring is too slow; simple scrapers miss the synthesis layer.",
      whoUsesIt: "Product teams, strategy consultants, startup founders, VC research teams",
      whyItMatters:
        "The swarm handoff pattern means each agent builds on the previous agent's findings. The Hiring agent knows what the Product agent found, so it can look for engineers with relevant skills — something a parallel pipeline can't do.",
    },
  },
]

export const categories = [
  {
    name: "RAG & Knowledge Graphs",
    projectIds: ["01"],
  },
  {
    name: "Multi-Agent Networks",
    projectIds: ["02", "05", "10"],
  },
  {
    name: "Human-in-the-Loop Systems",
    projectIds: ["03", "08", "09"],
  },
  {
    name: "Protocol Layer (MCP & A2A)",
    projectIds: ["04", "07"],
  },
  {
    name: "Memory & Monitoring",
    projectIds: ["06"],
  },
]

export function getProjectById(id) {
  return projects.find((p) => p.id === id)
}

export function getProjectsByIds(ids) {
  return ids.map((id) => getProjectById(id)).filter(Boolean)
}

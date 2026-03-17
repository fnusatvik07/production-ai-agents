"""
agent.py
~~~~~~~~
LangGraph StateGraph for the PR lifecycle agent.
Uses Send API for parallel analysis, interrupt() for confidence-gated HITL.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any, Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import Send, interrupt, Command
from pydantic import BaseModel
from typing_extensions import TypedDict

from .adr_store import ADRStore

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.75  # Below this → interrupt for human review


# ── State ──────────────────────────────────────────────────────────────────────

class PRAnalysisState(TypedDict):
    messages: Annotated[list, add_messages]

    # PR context
    pr_number: int
    repo_full_name: str
    diff: str
    pr_title: str
    pr_description: str

    # Analysis results
    relevant_adrs: list[dict]
    security_findings: list[dict]
    architecture_findings: list[dict]
    test_findings: list[dict]

    # Review output
    review_comments: list[dict]
    high_confidence_comments: list[dict]
    low_confidence_comments: list[dict]
    overall_verdict: Literal["approve", "request_changes", "comment"]
    posted_comment_ids: list[int]


class WorkerState(TypedDict):
    """State for individual parallel analysis workers."""
    diff: str
    relevant_adrs: list[dict]
    analysis_type: Literal["security", "architecture", "test"]


# ── LLM ───────────────────────────────────────────────────────────────────────

def get_llm() -> ChatAnthropic:
    return ChatAnthropic(model="claude-sonnet-4-6", temperature=0, max_tokens=4096)


# ── Nodes ─────────────────────────────────────────────────────────────────────

async def fetch_pr_content(state: PRAnalysisState) -> dict:
    """Fetch PR diff and metadata (already in state from webhook)."""
    logger.info("Reviewing PR #%d in %s", state["pr_number"], state["repo_full_name"])
    return {}


async def search_relevant_adrs(state: PRAnalysisState, adr_store: ADRStore) -> dict:
    """Find ADRs most relevant to the PR's changes."""
    query = f"{state['pr_title']}\n{state['pr_description']}\n{state['diff'][:1000]}"
    relevant_adrs = await adr_store.search(query, top_k=5)
    logger.info("Found %d relevant ADRs", len(relevant_adrs))
    return {"relevant_adrs": relevant_adrs}


def dispatch_analysis_workers(state: PRAnalysisState) -> list[Send]:
    """Fan out to parallel analysis nodes using Send API."""
    return [
        Send("analyze_security", {
            "diff": state["diff"],
            "relevant_adrs": state["relevant_adrs"],
            "analysis_type": "security",
        }),
        Send("analyze_architecture", {
            "diff": state["diff"],
            "relevant_adrs": state["relevant_adrs"],
            "analysis_type": "architecture",
        }),
        Send("analyze_tests", {
            "diff": state["diff"],
            "relevant_adrs": state["relevant_adrs"],
            "analysis_type": "test",
        }),
    ]


async def analyze_security(state: WorkerState) -> dict:
    """Security analysis worker."""
    llm = get_llm()

    class SecurityFinding(BaseModel):
        file: str
        line: int | None
        severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        description: str
        recommendation: str
        confidence: float

    class SecurityAnalysis(BaseModel):
        findings: list[SecurityFinding]

    structured_llm = llm.with_structured_output(SecurityAnalysis)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a security code reviewer. Analyze this diff for vulnerabilities. Include file/line refs and confidence scores (0-1)."),
        ("human", "Diff:\n{diff}"),
    ])

    result = await (prompt | structured_llm).ainvoke({"diff": state["diff"][:4000]})
    return {"security_findings": [f.model_dump() for f in result.findings]}


async def analyze_architecture(state: WorkerState) -> dict:
    """ADR compliance analysis worker."""
    llm = get_llm()

    if not state["relevant_adrs"]:
        return {"architecture_findings": []}

    adrs_text = "\n\n".join(
        f"### {adr['title']}\n{adr['content'][:500]}"
        for adr in state["relevant_adrs"]
    )

    class ArchFinding(BaseModel):
        adr_id: str
        adr_title: str
        violation_description: str
        file: str
        line: int | None
        severity: Literal["HIGH", "MEDIUM", "LOW"]
        recommendation: str
        confidence: float

    class ArchAnalysis(BaseModel):
        findings: list[ArchFinding]
        violations_found: bool

    structured_llm = llm.with_structured_output(ArchAnalysis)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an architecture reviewer. Check if this PR violates any of the provided ADRs. Be precise about which ADR is violated and where."),
        ("human", "ADRs:\n{adrs}\n\nPR Diff:\n{diff}"),
    ])

    result = await (prompt | structured_llm).ainvoke({
        "adrs": adrs_text,
        "diff": state["diff"][:4000],
    })
    return {"architecture_findings": [f.model_dump() for f in result.findings]}


async def analyze_tests(state: WorkerState) -> dict:
    """Test coverage analysis worker."""
    llm = get_llm()

    class TestFinding(BaseModel):
        function_name: str
        file: str
        description: str
        suggested_test: str
        confidence: float

    class TestAnalysis(BaseModel):
        findings: list[TestFinding]
        test_coverage_adequate: bool

    structured_llm = llm.with_structured_output(TestAnalysis)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a test engineer. Identify functions added/modified in this diff that lack adequate test coverage. Suggest specific test cases."),
        ("human", "Diff:\n{diff}"),
    ])

    result = await (prompt | structured_llm).ainvoke({"diff": state["diff"][:4000]})
    return {"test_findings": [f.model_dump() for f in result.findings]}


async def compile_review_comments(state: PRAnalysisState) -> dict:
    """Merge all analysis findings into review comments. Split by confidence."""
    all_findings = []

    for finding in state.get("security_findings", []):
        all_findings.append({**finding, "category": "security"})
    for finding in state.get("architecture_findings", []):
        all_findings.append({**finding, "category": "architecture"})
    for finding in state.get("test_findings", []):
        all_findings.append({**finding, "category": "test"})

    high_conf = [f for f in all_findings if f.get("confidence", 0) >= CONFIDENCE_THRESHOLD]
    low_conf = [f for f in all_findings if f.get("confidence", 0) < CONFIDENCE_THRESHOLD]

    # Determine overall verdict
    has_critical = any(f.get("severity") == "CRITICAL" for f in all_findings)
    has_high = any(f.get("severity") == "HIGH" for f in all_findings)

    verdict = "request_changes" if (has_critical or has_high) else "comment" if all_findings else "approve"

    logger.info(
        "Review compiled: %d high-conf, %d low-conf comments, verdict: %s",
        len(high_conf), len(low_conf), verdict,
    )

    return {
        "review_comments": all_findings,
        "high_confidence_comments": high_conf,
        "low_confidence_comments": low_conf,
        "overall_verdict": verdict,
    }


async def human_review_gate(state: PRAnalysisState) -> dict | Command:
    """Interrupt if there are low-confidence comments that need senior review."""
    if not state["low_confidence_comments"]:
        return {}

    decision = interrupt({
        "kind": "comment_review",
        "message": f"{len(state['low_confidence_comments'])} review comments need your approval before posting",
        "comments": state["low_confidence_comments"],
        "instructions": "approve_all / reject_all / review_each",
    })

    if decision.get("choice") == "approve_all":
        return {
            "high_confidence_comments": (
                state["high_confidence_comments"] + state["low_confidence_comments"]
            ),
            "low_confidence_comments": [],
        }
    elif decision.get("choice") == "review_each":
        approved = decision.get("approved_indices", [])
        approved_comments = [
            state["low_confidence_comments"][i]
            for i in approved
            if i < len(state["low_confidence_comments"])
        ]
        return {
            "high_confidence_comments": state["high_confidence_comments"] + approved_comments,
            "low_confidence_comments": [],
        }
    # reject_all: only post high-confidence comments
    return {"low_confidence_comments": []}


async def post_review_comments(state: PRAnalysisState) -> dict:
    """Post approved comments to GitHub PR via API."""
    comments_to_post = state["high_confidence_comments"]

    if not comments_to_post:
        logger.info("No comments to post for PR #%d", state["pr_number"])
        return {"posted_comment_ids": []}

    # In production: use PyGithub to post inline comments
    # gh = Github(token)
    # pr = gh.get_repo(repo).get_pull(pr_number)
    # for comment in comments_to_post:
    #     pr.create_review_comment(comment["description"], commit, comment["file"], comment["line"])

    logger.info("Would post %d comments to PR #%d", len(comments_to_post), state["pr_number"])
    return {"posted_comment_ids": list(range(len(comments_to_post)))}


# ── Graph ──────────────────────────────────────────────────────────────────────

def build_graph(adr_store: ADRStore):
    async def _search_adrs(state: PRAnalysisState) -> dict:
        return await search_relevant_adrs(state, adr_store)

    def should_interrupt(state: PRAnalysisState) -> Literal["human_review_gate", "post_review_comments"]:
        return "human_review_gate" if state.get("low_confidence_comments") else "post_review_comments"

    builder = StateGraph(PRAnalysisState)
    builder.add_node("fetch_pr_content", fetch_pr_content)
    builder.add_node("search_relevant_adrs", _search_adrs)
    builder.add_node("analyze_security", analyze_security)
    builder.add_node("analyze_architecture", analyze_architecture)
    builder.add_node("analyze_tests", analyze_tests)
    builder.add_node("compile_review_comments", compile_review_comments)
    builder.add_node("human_review_gate", human_review_gate)
    builder.add_node("post_review_comments", post_review_comments)

    builder.add_edge(START, "fetch_pr_content")
    builder.add_edge("fetch_pr_content", "search_relevant_adrs")

    # Fan out to parallel analysis workers
    builder.add_conditional_edges("search_relevant_adrs", dispatch_analysis_workers, ["analyze_security", "analyze_architecture", "analyze_tests"])

    # All workers → compile (LangGraph waits for all Send targets to complete)
    builder.add_edge("analyze_security", "compile_review_comments")
    builder.add_edge("analyze_architecture", "compile_review_comments")
    builder.add_edge("analyze_tests", "compile_review_comments")

    builder.add_conditional_edges("compile_review_comments", should_interrupt)
    builder.add_edge("human_review_gate", "post_review_comments")
    builder.add_edge("post_review_comments", END)

    from langgraph.checkpoint.memory import InMemorySaver
    return builder.compile(checkpointer=InMemorySaver())

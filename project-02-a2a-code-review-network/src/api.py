"""
api.py
~~~~~~
FastAPI orchestrator server.
Receives PR webhooks or manual review requests, fans out to A2A agents,
and optionally posts the aggregated review back to GitHub.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from github import Github
from pydantic import BaseModel

from .orchestrator import format_github_comment, orchestrate_review

logger = logging.getLogger(__name__)

app = FastAPI(
    title="A2A Code Review Orchestrator",
    description="Fans code diffs to specialist A2A agents and aggregates findings",
    version="0.1.0",
)


# ── Models ─────────────────────────────────────────────────────────────────────

class ManualReviewRequest(BaseModel):
    diff: str
    pr_url: str | None = None
    post_comment: bool = False


class ReviewResponse(BaseModel):
    review_id: str
    total_findings: int
    critical: int
    high: int
    overall_risk: str
    total_latency_ms: float
    findings: list[dict]
    agent_summaries: dict[str, Any]
    github_comment: str | None = None


# ── GitHub Webhook ─────────────────────────────────────────────────────────────

def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str = Header(default=""),
):
    """Receive GitHub PR webhook events."""
    body = await request.body()
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")

    if secret and not verify_github_signature(body, x_hub_signature_256, secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if x_github_event != "pull_request":
        return {"status": "ignored", "event": x_github_event}

    payload = json.loads(body)
    action = payload.get("action", "")

    if action not in {"opened", "synchronize"}:
        return {"status": "ignored", "action": action}

    # Fetch the diff from GitHub
    pr_url = payload["pull_request"]["html_url"]
    diff_url = payload["pull_request"]["diff_url"]

    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"token {os.environ.get('GITHUB_TOKEN', '')}"}
        diff_response = await client.get(diff_url, headers=headers)
        diff = diff_response.text

    # Run the review
    logger.info("Reviewing PR: %s", pr_url)
    review = await orchestrate_review(diff)
    comment = format_github_comment(review)

    # Post comment to GitHub
    github_token = os.environ.get("GITHUB_TOKEN", "")
    if github_token:
        gh = Github(github_token)
        repo_full_name = payload["repository"]["full_name"]
        pr_number = payload["pull_request"]["number"]
        repo = gh.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        pr.create_issue_comment(comment)
        logger.info("Posted review comment to PR #%d", pr_number)

    return {"status": "reviewed", "review_id": review["review_id"], "pr_url": pr_url}


# ── Manual Review Endpoint ─────────────────────────────────────────────────────

@app.post("/review", response_model=ReviewResponse)
async def manual_review(request: ManualReviewRequest):
    """Manually trigger a code review for a given diff."""
    if not request.diff.strip():
        raise HTTPException(status_code=400, detail="diff cannot be empty")

    logger.info("Manual review request, diff length=%d", len(request.diff))
    review = await orchestrate_review(request.diff)
    comment = format_github_comment(review)

    # Optionally post to GitHub if pr_url provided
    if request.post_comment and request.pr_url:
        github_token = os.environ.get("GITHUB_TOKEN", "")
        if github_token:
            try:
                # Parse owner/repo/number from URL
                parts = request.pr_url.rstrip("/").split("/")
                pr_number = int(parts[-1])
                repo_name = f"{parts[-4]}/{parts[-3]}"
                gh = Github(github_token)
                repo = gh.get_repo(repo_name)
                pr = repo.get_pull(pr_number)
                pr.create_issue_comment(comment)
            except Exception as e:
                logger.warning("Failed to post GitHub comment: %s", e)

    return ReviewResponse(
        **review,
        github_comment=comment,
    )


@app.get("/health")
async def health():
    return {"status": "ok", "agents": list(["security", "style", "test"])}

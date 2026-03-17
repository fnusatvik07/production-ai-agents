"""
kubectl_mcp.py
~~~~~~~~~~~~~~
FastMCP server exposing kubectl operations as MCP tools.
All destructive commands require explicit approval before execution.

Run: uv run python -m src.mcp_servers.kubectl_mcp
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex

from fastmcp import FastMCP, Context

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "kubectl-mcp",
    dependencies=["fastmcp"],
)

# Commands that are classified as dangerous and must be flagged
DANGEROUS_PATTERNS = [
    "delete", "drain", "cordon", "taint",
    "scale --replicas=0", "patch", "replace",
]


def is_dangerous(command: str) -> bool:
    return any(pattern in command for pattern in DANGEROUS_PATTERNS)


@mcp.tool
async def kubectl_get(resource: str, namespace: str = "default", ctx: Context = None) -> str:
    """
    Get Kubernetes resources. Safe read-only operation.

    Args:
        resource: Resource type and optional name (e.g., "pods", "pods api-gateway-xxx", "nodes")
        namespace: Kubernetes namespace (default: "default")
    """
    cmd = f"kubectl get {resource} -n {namespace} -o json"
    await ctx.info(f"Running: {cmd}")
    return await _run_kubectl(cmd)


@mcp.tool
async def kubectl_describe(resource: str, name: str, namespace: str = "default", ctx: Context = None) -> str:
    """
    Describe a Kubernetes resource in detail.

    Args:
        resource: Resource type (e.g., "pod", "deployment", "service")
        name: Resource name
        namespace: Kubernetes namespace
    """
    cmd = f"kubectl describe {resource} {name} -n {namespace}"
    await ctx.info(f"Running: {cmd}")
    return await _run_kubectl(cmd)


@mcp.tool
async def kubectl_top_pods(namespace: str = "default", ctx: Context = None) -> str:
    """
    Get CPU and memory usage for all pods in a namespace.

    Args:
        namespace: Kubernetes namespace
    """
    cmd = f"kubectl top pods -n {namespace}"
    await ctx.info(f"Running: {cmd}")
    return await _run_kubectl(cmd)


@mcp.tool
async def kubectl_logs(
    pod: str,
    namespace: str = "default",
    tail: int = 100,
    container: str | None = None,
    ctx: Context = None,
) -> str:
    """
    Fetch pod logs.

    Args:
        pod: Pod name
        namespace: Kubernetes namespace
        tail: Number of recent log lines to return
        container: Container name (optional, for multi-container pods)
    """
    container_flag = f"-c {container}" if container else ""
    cmd = f"kubectl logs {pod} -n {namespace} --tail={tail} {container_flag}"
    await ctx.info(f"Running: {cmd}")
    return await _run_kubectl(cmd)


@mcp.tool
async def kubectl_rollout_status(deployment: str, namespace: str = "default", ctx: Context = None) -> str:
    """
    Check the rollout status of a deployment.

    Args:
        deployment: Deployment name
        namespace: Kubernetes namespace
    """
    cmd = f"kubectl rollout status deployment/{deployment} -n {namespace} --timeout=30s"
    await ctx.info(f"Running: {cmd}")
    return await _run_kubectl(cmd)


@mcp.tool
async def kubectl_delete_pod(pod: str, namespace: str = "default", ctx: Context = None) -> dict:
    """
    Delete a pod (DANGEROUS — requires human approval before execution).
    The pod will be recreated by its controller.

    Args:
        pod: Pod name to delete
        namespace: Kubernetes namespace

    Returns dict with 'requires_approval' flag when dangerous.
    """
    cmd = f"kubectl delete pod {pod} -n {namespace}"
    await ctx.warning(f"DANGEROUS operation requested: {cmd}")

    return {
        "requires_approval": True,
        "command": cmd,
        "danger_level": "HIGH",
        "effect": f"Pod {pod} in {namespace} will be terminated. Controller will recreate it.",
        "reversible": True,
    }


@mcp.tool
async def kubectl_rollout_restart(deployment: str, namespace: str = "default", ctx: Context = None) -> dict:
    """
    Restart all pods in a deployment via rolling restart (DANGEROUS).

    Args:
        deployment: Deployment name
        namespace: Kubernetes namespace

    Returns dict with 'requires_approval' flag.
    """
    cmd = f"kubectl rollout restart deployment/{deployment} -n {namespace}"
    await ctx.warning(f"DANGEROUS operation requested: {cmd}")

    return {
        "requires_approval": True,
        "command": cmd,
        "danger_level": "MEDIUM",
        "effect": f"Rolling restart of all pods in {deployment}. Brief service disruption possible.",
        "reversible": True,
    }


async def kubectl_execute_approved(command: str) -> str:
    """Execute a pre-approved kubectl command. NOT exposed as MCP tool — internal only."""
    logger.info("Executing approved kubectl command: %s", command)
    return await _run_kubectl(command)


async def _run_kubectl(cmd: str) -> str:
    """Run a kubectl command and return stdout/stderr."""
    # In production: uses the real kubectl with proper kubeconfig
    # Here we return a simulated response for development
    if os.environ.get("KUBECTL_DRY_RUN", "true").lower() == "true":
        return json.dumps({
            "simulated": True,
            "command": cmd,
            "output": f"[DRY RUN] Would execute: {cmd}",
            "note": "Set KUBECTL_DRY_RUN=false to execute real kubectl commands",
        })

    try:
        process = await asyncio.create_subprocess_exec(
            *shlex.split(cmd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30.0)
        if process.returncode != 0:
            return f"ERROR (exit {process.returncode}): {stderr.decode()}"
        return stdout.decode()
    except asyncio.TimeoutError:
        return "ERROR: kubectl command timed out after 30s"
    except Exception as e:
        return f"ERROR: {e}"


# ── Resources ─────────────────────────────────────────────────────────────────

@mcp.resource("kubectl://cluster/info")
async def cluster_info() -> str:
    """Current cluster connection info."""
    cluster = os.environ.get("EKS_CLUSTER_NAME", "unknown-cluster")
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    return json.dumps({"cluster": cluster, "region": region, "mode": "dry-run" if os.environ.get("KUBECTL_DRY_RUN", "true") == "true" else "live"})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("KUBECTL_MCP_PORT", "9010"))
    logger.info("Starting kubectl MCP server on port %d", port)
    mcp.run(transport="http", port=port)

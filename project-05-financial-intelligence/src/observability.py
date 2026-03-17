"""
observability.py
~~~~~~~~~~~~~~~~
Arize Phoenix setup for self-hosted agent observability.
Captures all LLM calls, tool calls, and agent transitions as OTel spans.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def setup_phoenix_tracing() -> None:
    """
    Initialize Arize Phoenix for distributed tracing.
    Traces are viewable at http://localhost:6006 (Phoenix UI).
    """
    try:
        import phoenix as px
        from phoenix.otel import register
        from opentelemetry.instrumentation.openai import OpenAIInstrumentor

        phoenix_endpoint = os.environ.get("PHOENIX_ENDPOINT", "http://localhost:6006/v1/traces")

        tracer_provider = register(
            project_name="financial-intelligence",
            endpoint=phoenix_endpoint,
        )

        # Auto-instrument OpenAI SDK calls (used by AutoGen)
        OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)

        logger.info("Phoenix tracing initialized. View at http://localhost:6006")

    except ImportError:
        logger.warning(
            "arize-phoenix or opentelemetry-instrumentation-openai not installed. "
            "Run: uv add arize-phoenix opentelemetry-instrumentation-openai"
        )
    except Exception as e:
        logger.warning("Phoenix tracing setup failed: %s", e)


def get_session_tracer():
    """Get an OTel tracer for manual span creation."""
    from opentelemetry import trace
    return trace.get_tracer("financial.intelligence")

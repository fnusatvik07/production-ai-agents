"""
tracer.py
~~~~~~~~~
OpenTelemetry tracing for MCP tool calls using GenAI semantic conventions.
Produces spans compatible with Grafana Tempo / Jaeger / Datadog.
"""

from __future__ import annotations

import functools
import json
import logging
import time
from typing import Any, Callable

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

_tracer: trace.Tracer | None = None


def setup_tracing(service_name: str = "mcp-enterprise-gateway", otlp_endpoint: str = "http://localhost:4317") -> None:
    """Initialize OTel tracing. Call once at startup."""
    global _tracer

    resource = Resource.create({
        "service.name": service_name,
        "service.version": "0.1.0",
        "deployment.environment": "development",
    })

    provider = TracerProvider(resource=resource)

    try:
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("OTel tracing → %s", otlp_endpoint)
    except Exception as e:
        logger.warning("Could not connect to OTel collector: %s. Tracing disabled.", e)

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("mcp.gateway")


def get_tracer() -> trace.Tracer:
    global _tracer
    if _tracer is None:
        setup_tracing()
    return _tracer


def traced(func: Callable) -> Callable:
    """
    Decorator to add OTel spans to MCP tool functions.
    Uses GenAI semantic conventions (gen_ai.*) for tool call attributes.

    Usage:
        @traced
        @cached(ttl=300)
        @mcp.tool
        async def my_tool(arg: str) -> dict: ...
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        tracer = get_tracer()
        tool_name = func.__name__

        # Build input summary (exclude ctx from span attributes)
        tool_input = {k: v for k, v in kwargs.items() if k != "ctx"}
        input_repr = json.dumps(tool_input, default=str)[:256]  # cap at 256 chars

        with tracer.start_as_current_span(
            f"mcp.tool_call",
            kind=trace.SpanKind.SERVER,
        ) as span:
            # GenAI semantic conventions
            span.set_attribute("gen_ai.system", "mcp")
            span.set_attribute("gen_ai.tool.name", tool_name)
            span.set_attribute("gen_ai.tool.input", input_repr)
            span.set_attribute("mcp.server", "enterprise-gateway")

            start_time = time.monotonic()
            try:
                result = await func(*args, **kwargs)

                # Record output metadata
                output_str = json.dumps(result, default=str) if not isinstance(result, str) else result
                span.set_attribute("gen_ai.tool.output_length", len(output_str))
                span.set_attribute("gen_ai.tool.success", True)

                # Check if result came from cache
                if hasattr(func, "_cache_ttl"):
                    span.set_attribute("cache.configured_ttl", func._cache_ttl)

                return result

            except Exception as e:
                span.record_exception(e)
                span.set_attribute("gen_ai.tool.success", False)
                span.set_attribute("error.type", type(e).__name__)
                raise

            finally:
                latency_ms = (time.monotonic() - start_time) * 1000
                span.set_attribute("gen_ai.tool.latency_ms", round(latency_ms, 2))

    return wrapper

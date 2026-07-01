"""OpenTelemetry tracing for voice turns and multi-turn conversations.

Export to Langfuse (or any OTLP backend) via standard env vars:

    OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel
    OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic <base64(public_key:secret_key)>
    OTEL_SERVICE_NAME=maya-voice-stack
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator
from uuid import uuid4

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_tracer_name = "maya.voice"
_initialized = False


def init_tracing(*, service_name: str = "maya-voice-stack") -> trace.Tracer:
    """Configure OTLP trace export when an endpoint is set; always return a tracer."""
    global _initialized
    tracer = trace.get_tracer(_tracer_name)
    if _initialized:
        return tracer

    resource = Resource.create(
        {
            "service.name": os.getenv("OTEL_SERVICE_NAME", service_name),
            "deployment.environment": os.getenv("ENV", "development"),
        }
    )
    provider = TracerProvider(resource=resource)
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        except ImportError:
            pass
    trace.set_tracer_provider(provider)
    _initialized = True
    return tracer


def new_conversation_id() -> str:
    return uuid4().hex


def new_turn_id() -> str:
    return uuid4().hex[:12]


@contextmanager
def span(
    name: str,
    *,
    conversation_id: str | None = None,
    turn_id: str | None = None,
    **attrs: Any,
) -> Iterator[trace.Span]:
    tracer = init_tracing()
    with tracer.start_as_current_span(name) as current:
        if conversation_id:
            current.set_attribute("voice.conversation_id", conversation_id)
        if turn_id:
            current.set_attribute("voice.turn_id", turn_id)
        for key, value in attrs.items():
            if value is not None:
                current.set_attribute(key, value)
        yield current


def current_trace_id() -> str | None:
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None
    return format(ctx.trace_id, "032x")

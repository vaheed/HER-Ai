from __future__ import annotations

from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter


_initialized = False


def setup_tracing(service_name: str) -> None:
    """Setup a basic OpenTelemetry tracer provider with console exporter."""

    global _initialized
    if _initialized:
        return

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    _initialized = True


def get_tracer(name: Optional[str] = None) -> trace.Tracer:
    """Get a tracer for the provided module name."""

    return trace.get_tracer(name or "her")

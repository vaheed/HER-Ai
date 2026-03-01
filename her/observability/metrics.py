from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUEST_COUNTER = Counter(
    "her_requests_total",
    "Total API requests",
    labelnames=("route",),
)

PROVIDER_CALL_COUNTER = Counter(
    "her_provider_calls_total",
    "Provider call count",
    labelnames=("provider", "status"),
)

PROVIDER_LATENCY_MS = Histogram(
    "her_provider_latency_ms",
    "Provider latency in milliseconds",
    labelnames=("provider",),
    buckets=(25, 50, 100, 250, 500, 1000, 2000, 5000),
)

PROVIDER_COST_USD = Counter(
    "her_provider_cost_usd_total",
    "Estimated provider cost in USD",
    labelnames=("provider",),
)


def record_provider_call(provider: str, success: bool, latency_ms: int, cost_usd: float) -> None:
    """Record a provider invocation with status, latency, and cost."""

    status = "success" if success else "failure"
    PROVIDER_CALL_COUNTER.labels(provider=provider, status=status).inc()
    PROVIDER_LATENCY_MS.labels(provider=provider).observe(float(latency_ms))
    if cost_usd > 0:
        PROVIDER_COST_USD.labels(provider=provider).inc(cost_usd)


def metrics_payload() -> bytes:
    """Return Prometheus payload bytes."""

    return generate_latest()


def metrics_content_type() -> str:
    """Return Prometheus payload content type."""

    return CONTENT_TYPE_LATEST

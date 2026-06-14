"""Observability wiring (Phase 5): Prometheus metrics + OpenTelemetry traces.

The only place the prometheus / opentelemetry libraries are imported — same
single-adapter rule the LLM and JWT clients follow, so the rest of the app
stays free of vendor imports and easy to test.
"""

import logging

from fastapi import FastAPI

from app.config import Settings

logger = logging.getLogger(__name__)


def setup_metrics(app: FastAPI) -> None:
    """Expose Prometheus metrics at /metrics (request count, latency, in-progress).

    Prometheus scrapes this endpoint; Grafana charts it — parity with the Go
    services' promhttp /metrics.
    """
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app)
    logger.info("metrics enabled at /metrics")


def setup_tracing(app: FastAPI, settings: Settings) -> None:
    """Wire OpenTelemetry traces to an OTLP collector (Jaeger).

    No-op when OTEL_EXPORTER_OTLP_ENDPOINT is empty, so local dev without a
    collector still runs. Instruments FastAPI (the incoming server span) AND
    httpx (the outgoing spans to auth/gateway), and propagates the trace context
    on those outgoing calls — so one request shows up as a SINGLE distributed
    trace across front -> brain -> auth -> gateway.

    Must run before the lifespan creates its httpx.AsyncClient: HTTPXClient
    instrumentation patches the httpx classes, and only clients built after the
    patch are traced. main.py calls this at import time, before startup.
    """
    if not settings.otel_exporter_otlp_endpoint:
        logger.info("tracing disabled: OTEL_EXPORTER_OTLP_ENDPOINT not set")
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": settings.otel_service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
        )
    )
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    logger.info(
        "tracing enabled: service=%s exporter=%s",
        settings.otel_service_name,
        settings.otel_exporter_otlp_endpoint,
    )

# Observability

This document outlines recommended observability additions for RuggyLab OS.

Metrics
- Expose a Prometheus `/metrics` endpoint from the application (e.g. using `prometheus_client`).
- Instrument request durations, error counts, DB latency, and ML inference timings.

Logging
- Use structured JSON logs (e.g. `python-json-logger`) written to stdout for container environments.
- Include request IDs and user identifiers where appropriate (avoid PII).

Tracing
- Add optional OpenTelemetry tracing with an OTLP collector for distributed traces.

Error tracking
- Add Sentry integration (DSN in secrets) for capturing exceptions and performance traces.

Dashboards & Alerts
- Prometheus is part of the core stack and scrapes `/metrics` directly; RUGGYLAB is fully
  supported without any dashboarding layer.
- Grafana is an **optional external overlay**, not a distributed component of RUGGYLAB OS.
  Operators who want dashboards pull the image from its own publisher and run it
  themselves: `docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d`.
  Provisioning and RUGGYLAB dashboards are supplied read-only by that overlay.
- Set up alerting for high error rates, elevated latency, and job failures — in Grafana if
  the overlay is used, or directly in Prometheus/Alertmanager otherwise.

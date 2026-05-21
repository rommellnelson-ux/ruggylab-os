"""
Prometheus metrics and monitoring for RuggyLab OS.

Provides metrics for requests, database operations, and custom application metrics.
"""

from prometheus_client import Counter, Gauge, Histogram, start_http_server


class MetricsRegistry:
    """Central registry for all Prometheus metrics."""

    # HTTP metrics
    http_requests_total = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status"],
    )

    http_request_duration_seconds = Histogram(
        "http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "endpoint"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    )

    # Database metrics
    db_queries_total = Counter(
        "db_queries_total",
        "Total database queries",
        ["operation", "table"],
    )

    db_query_duration_seconds = Histogram(
        "db_query_duration_seconds",
        "Database query duration in seconds",
        ["operation", "table"],
        buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
    )

    db_connection_pool_size = Gauge(
        "db_connection_pool_size",
        "Database connection pool size",
    )

    db_active_connections = Gauge(
        "db_active_connections",
        "Active database connections",
    )

    # Application metrics
    patients_count = Gauge(
        "patients_count",
        "Total number of patients",
    )

    samples_count = Gauge(
        "samples_count",
        "Total number of samples",
    )

    results_count = Gauge(
        "results_count",
        "Total number of results",
    )

    audit_events_total = Counter(
        "audit_events_total",
        "Total audit events",
        ["event_type"],
    )

    malaria_analyses_total = Counter(
        "malaria_analyses_total",
        "Total malaria analyses",
        ["status"],
    )

    # Error metrics
    errors_total = Counter(
        "errors_total",
        "Total errors",
        ["error_type", "endpoint"],
    )

    # Authentication metrics
    authentication_attempts_total = Counter(
        "authentication_attempts_total",
        "Total authentication attempts",
        ["status"],
    )

    rate_limit_denied_total = Counter(
        "rate_limit_denied_total",
        "Total denied requests due to rate limiting",
        ["endpoint"],
    )

    active_users = Gauge(
        "active_users",
        "Number of active users",
    )

    # Cache metrics
    cache_hits_total = Counter(
        "cache_hits_total",
        "Total cache hits",
        ["cache_name"],
    )

    cache_misses_total = Counter(
        "cache_misses_total",
        "Total cache misses",
        ["cache_name"],
    )

    # Business metrics
    reagent_stock_levels = Gauge(
        "reagent_stock_levels",
        "Reagent stock levels",
        ["reagent_name"],
    )

    equipment_status = Gauge(
        "equipment_status",
        "Equipment status (1=online, 0=offline)",
        ["equipment_name"],
    )


def init_metrics_server(port: int = 8001) -> None:
    """Start Prometheus metrics HTTP server."""
    start_http_server(port)


def record_request_metrics(method: str, endpoint: str, status: int, duration: float) -> None:
    """Record HTTP request metrics."""
    MetricsRegistry.http_requests_total.labels(
        method=method,
        endpoint=endpoint,
        status=status,
    ).inc()

    MetricsRegistry.http_request_duration_seconds.labels(
        method=method,
        endpoint=endpoint,
    ).observe(duration)


def record_db_query(operation: str, table: str, duration: float) -> None:
    """Record database query metrics."""
    MetricsRegistry.db_queries_total.labels(
        operation=operation,
        table=table,
    ).inc()

    MetricsRegistry.db_query_duration_seconds.labels(
        operation=operation,
        table=table,
    ).observe(duration)


def record_error(error_type: str, endpoint: str) -> None:
    """Record error metrics."""
    MetricsRegistry.errors_total.labels(
        error_type=error_type,
        endpoint=endpoint,
    ).inc()


def record_auth_attempt(success: bool) -> None:
    """Record authentication attempt."""
    status = "success" if success else "failure"
    MetricsRegistry.authentication_attempts_total.labels(status=status).inc()


def record_cache_hit(cache_name: str) -> None:
    """Record cache hit."""
    MetricsRegistry.cache_hits_total.labels(cache_name=cache_name).inc()


def record_cache_miss(cache_name: str) -> None:
    """Record cache miss."""
    MetricsRegistry.cache_misses_total.labels(cache_name=cache_name).inc()


def record_rate_limit_denied(endpoint: str) -> None:
    """Record rate limit denial metrics."""
    MetricsRegistry.rate_limit_denied_total.labels(endpoint=endpoint).inc()


def update_reagent_stock(reagent_name: str, quantity: float) -> None:
    """Update reagent stock level."""
    MetricsRegistry.reagent_stock_levels.labels(reagent_name=reagent_name).set(quantity)


def update_equipment_status(equipment_name: str, is_online: bool) -> None:
    """Update equipment status."""
    status = 1.0 if is_online else 0.0
    MetricsRegistry.equipment_status.labels(equipment_name=equipment_name).set(status)

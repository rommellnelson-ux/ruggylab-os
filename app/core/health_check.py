"""
Health checks and status endpoints for RuggyLab OS.

Provides liveness, readiness, and detailed health check endpoints.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.metrics import MetricsRegistry


class HealthStatus(BaseModel):
    """Health check status."""

    status: str  # "healthy", "degraded", "unhealthy"
    timestamp: datetime
    uptime_seconds: float
    version: str
    checks: dict[str, Any]


class HealthCheckService:
    """Service for performing health checks."""

    def __init__(self, start_time: datetime) -> None:
        self.start_time = start_time

    def check_database(self, db: Session) -> tuple[bool, dict[str, Any]]:
        """Check database connectivity."""
        try:
            # Simple query to test connectivity
            from sqlalchemy import text
            db.execute(text("SELECT 1"))
            return True, {
                "status": "healthy",
                "message": "Database connection successful",
            }
        except Exception as exc:
            return False, {
                "status": "unhealthy",
                "message": f"Database check failed: {str(exc)}",
            }

    def check_cache(self) -> tuple[bool, dict[str, Any]]:
        """Check cache connectivity (placeholder for Redis/Memcached)."""
        # TODO: Implement actual cache check
        return True, {
            "status": "healthy",
            "message": "Cache check passed (not yet implemented)",
        }

    def check_disk_space(self) -> tuple[bool, dict[str, Any]]:
        """Check available disk space."""
        import shutil

        stat = shutil.disk_usage("/")
        free_percent = (stat.free / stat.total) * 100

        if free_percent < 5:
            return False, {
                "status": "unhealthy",
                "message": f"Low disk space: {free_percent:.1f}%",
                "free_percent": free_percent,
            }
        elif free_percent < 10:
            return False, {
                "status": "degraded",
                "message": f"Disk space getting low: {free_percent:.1f}%",
                "free_percent": free_percent,
            }

        return True, {
            "status": "healthy",
            "message": "Disk space available",
            "free_percent": free_percent,
        }

    def check_memory(self) -> tuple[bool, dict[str, Any]]:
        """Check available memory."""
        import psutil

        memory = psutil.virtual_memory()
        percent = memory.percent

        if percent > 90:
            return False, {
                "status": "unhealthy",
                "message": f"High memory usage: {percent}%",
                "percent": percent,
            }
        elif percent > 75:
            return False, {
                "status": "degraded",
                "message": f"Memory usage elevated: {percent}%",
                "percent": percent,
            }

        return True, {
            "status": "healthy",
            "message": "Memory usage normal",
            "percent": percent,
        }

    def get_health(self, db: Session, app_version: str) -> HealthStatus:
        """Perform comprehensive health check."""
        uptime = (datetime.now(UTC) - self.start_time).total_seconds()

        db_ok, db_check = self.check_database(db)
        cache_ok, cache_check = self.check_cache()
        disk_ok, disk_check = self.check_disk_space()
        mem_ok, mem_check = self.check_memory()

        checks: dict[str, dict[str, Any]] = {
            "database": db_check,
            "cache": cache_check,
            "disk_space": disk_check,
            "memory": mem_check,
        }

        # Determine overall status
        unhealthy_checks = [c for c in checks.values() if c.get("status") == "unhealthy"]
        degraded_checks = [c for c in checks.values() if c.get("status") == "degraded"]

        if unhealthy_checks:
            overall_status = "unhealthy"
        elif degraded_checks:
            overall_status = "degraded"
        else:
            overall_status = "healthy"

        return HealthStatus(
            status=overall_status,
            timestamp=datetime.now(UTC),
            uptime_seconds=uptime,
            version=app_version,
            checks=checks,
        )

    def get_readiness(self, db: Session) -> dict[str, Any]:
        """Check if service is ready to accept traffic."""
        db_ok, db_status = self.check_database(db)
        cache_ok, cache_status = self.check_cache()

        ready = db_ok and cache_ok

        return {
            "ready": ready,
            "database": db_status,
            "cache": cache_status,
        }

    def get_liveness(self) -> dict[str, Any]:
        """Check if service is alive (simple check)."""
        uptime = (datetime.now(UTC) - self.start_time).total_seconds()

        return {
            "alive": True,
            "uptime_seconds": uptime,
            "timestamp": datetime.now(UTC),
        }

    def get_metrics_summary(self) -> dict[str, Any]:
        """Get summary of application metrics."""
        registry = MetricsRegistry

        return {
            "http_requests_total": sum(
                registry.http_requests_total._metrics.values(),
            ),
            "errors_total": sum(
                registry.errors_total._metrics.values(),
            ),
            "db_queries_total": sum(
                registry.db_queries_total._metrics.values(),
            ),
            "active_users": registry.active_users._value.get(),
            "timestamp": datetime.now(UTC),
        }

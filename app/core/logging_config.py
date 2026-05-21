"""
Structured logging configuration with JSON format for production.

Supports multiple outputs: console, file, and structured JSON logging.
"""

import sys
from logging.config import dictConfig
from typing import Any

import structlog


def configure_logging(
    level: str = "INFO",
    json_logs: bool = True,
    log_file: str | None = None,
) -> None:
    """
    Configure structured logging with structlog.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_logs: Whether to output JSON formatted logs
        log_file: Optional file path to write logs to
    """
    # Standard library logging configuration
    stdlib_config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "plain": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.dev.ConsoleRenderer(),
            },
            "json": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.processors.JSONRenderer(),
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json" if json_logs else "plain",
                "stream": sys.stdout,
            },
        },
        "root": {
            "handlers": ["console"],
            "level": level,
        },
    }

    # Add file handler if specified
    if log_file:
        import os

        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
        stdlib_config["handlers"]["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "json",
            "filename": log_file,
            "maxBytes": 10_485_760,  # 10MB
            "backupCount": 5,
        }
        stdlib_config["root"]["handlers"].append("file")

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Apply logging configuration
    dictConfig(stdlib_config)


def get_logger(name: str) -> Any:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


class StructuredLogger:
    """Helper class for structured logging with context."""

    def __init__(self, name: str) -> None:
        self.logger = get_logger(name)

    def log_event(
        self,
        event: str,
        level: str = "info",
        **context: Any,
    ) -> None:
        """Log an event with context."""
        log_func = getattr(self.logger, level.lower(), self.logger.info)
        log_func(event, **context)

    def log_request(self, request_id: str, method: str, path: str, **extra: Any) -> None:
        """Log an HTTP request."""
        self.logger.info(
            "http_request",
            request_id=request_id,
            method=method,
            path=path,
            **extra,
        )

    def log_response(
        self,
        request_id: str,
        status_code: int,
        duration_ms: float,
        **extra: Any,
    ) -> None:
        """Log an HTTP response."""
        self.logger.info(
            "http_response",
            request_id=request_id,
            status_code=status_code,
            duration_ms=duration_ms,
            **extra,
        )

    def log_exception(self, exception: Exception, context: str = "", **extra: Any) -> None:
        """Log an exception with context."""
        self.logger.exception(
            "exception",
            exception_type=type(exception).__name__,
            exception_message=str(exception),
            context=context,
            **extra,
        )

    def log_database_query(
        self,
        query: str,
        duration_ms: float,
        params: dict[str, Any] | None = None,
        **extra: Any,
    ) -> None:
        """Log a database query."""
        self.logger.info(
            "db_query",
            query=query,
            duration_ms=duration_ms,
            params=params,
            **extra,
        )

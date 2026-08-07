"""JSON structured logging setup.

All logs are emitted as single-line JSON so they can be shipped to
Logstash/Loki/CloudWatch and queried by `env`, `tenant_id` etc. later. The
`trace_id` hook is where RAG-call tracing (LangSmith or a custom logger) will
attach per-request IDs in Phase 4.
"""
import json
import logging
import sys


class JsonFormatter(logging.Formatter):
    """Cloud-friendly single-line JSON log formatter (stdout)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Merge arbitrary kwargs passed to logger.info("...", **extra).
        if hasattr(record, "extra_fields"):
            payload.update(record.extra_fields)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger to emit JSON to stdout once."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()  # avoid duplicate handlers across app reloads
    root.addHandler(handler)
    root.setLevel(level.upper())
    # Give sqlalchemy/celery quieter defaults unless DEBUG.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aioredis").setLevel(logging.WARNING)
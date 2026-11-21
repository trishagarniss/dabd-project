"""Structured JSON logging: timestamp, severity, service, run_id (F-14)."""
from __future__ import annotations

import json
import logging
from typing import Any

from src.common.config import RUN_ID, SERVICE_NAME, STRUCTURED_LOG


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "severity": record.levelname,
            "service": getattr(record, "service", SERVICE_NAME),
            "run_id": getattr(record, "run_id", RUN_ID),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("job", "batch_id", "event_id", "dataset", "status", "error"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def get_logger(service: str | None = None) -> logging.Logger:
    name = service or SERVICE_NAME
    logger = logging.getLogger(f"fdp.{name}")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False

    stream = logging.StreamHandler()
    stream.setFormatter(JsonFormatter())
    logger.addHandler(stream)

    try:
        file_handler = logging.FileHandler(STRUCTURED_LOG, encoding="utf-8")
        file_handler.setFormatter(JsonFormatter())
        logger.addHandler(file_handler)
    except OSError:
        pass

    return logging.LoggerAdapter(logger, {"service": name, "run_id": RUN_ID})  # type: ignore[return-value]


def log_error(logger: logging.Logger, message: str, error: Exception | None = None, **extra: Any) -> None:
    """Log an error with correlation fields so it can be traced to a run/input (F-14)."""
    logger.error(message, extra={**extra, "error": str(error) if error else None, "status": "ERROR"})

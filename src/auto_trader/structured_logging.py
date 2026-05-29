from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REQUIRED_EVENT_KEYS = {
    "ts",
    "level",
    "event",
    "symbol",
    "regime",
    "order_id",
    "trace_id",
    "message",
}


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event": getattr(record, "event", "generic"),
            "symbol": getattr(record, "symbol", ""),
            "regime": getattr(record, "regime", ""),
            "order_id": getattr(record, "order_id", ""),
            "trace_id": getattr(record, "trace_id", ""),
            "message": record.getMessage(),
        }
        return json.dumps(payload, ensure_ascii=True)


def build_logger(name: str, jsonl_path: str, level: int = logging.INFO) -> logging.Logger:
    Path(jsonl_path).parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()

    handler = logging.FileHandler(jsonl_path, encoding="utf-8")
    handler.setFormatter(JsonLineFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def validate_log_event(event: dict[str, Any]) -> bool:
    missing = REQUIRED_EVENT_KEYS.difference(event.keys())
    return not missing

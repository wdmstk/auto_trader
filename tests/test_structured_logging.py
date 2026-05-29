from __future__ import annotations

import json
import logging
from pathlib import Path

from auto_trader.structured_logging import build_logger, validate_log_event


def test_structured_log_contains_required_keys(tmp_path: Path) -> None:
    log_file = tmp_path / "events.jsonl"
    logger = build_logger("test_logger", str(log_file), level=logging.INFO)
    logger.info(
        "order created",
        extra={
            "event": "order_created",
            "symbol": "BTCUSDT",
            "regime": "RANGE",
            "order_id": "oid-1",
            "trace_id": "tid-1",
        },
    )

    line = log_file.read_text(encoding="utf-8").strip()
    payload = json.loads(line)
    assert validate_log_event(payload) is True

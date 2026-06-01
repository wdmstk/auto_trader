from __future__ import annotations

import json
from pathlib import Path


def is_drift_trade_blocked(report_path: str | Path | None) -> bool:
    if report_path is None:
        return False
    p = Path(report_path)
    if not p.exists():
        return False
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(obj, dict):
        return False
    return bool(obj.get("drift_trade_block", False))

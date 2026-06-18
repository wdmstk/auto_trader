from __future__ import annotations

import json
from pathlib import Path

from auto_trader.drift.gate import is_drift_trade_blocked


def test_returns_false_when_report_path_is_none() -> None:
    assert is_drift_trade_blocked(None) is False


def test_returns_false_when_report_does_not_exist(tmp_path: Path) -> None:
    assert is_drift_trade_blocked(tmp_path / "missing.json") is False


def test_returns_false_when_report_is_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{broken", encoding="utf-8")
    assert is_drift_trade_blocked(path) is False


def test_returns_false_when_report_is_not_dict(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert is_drift_trade_blocked(path) is False


def test_returns_false_when_drift_trade_block_is_false(tmp_path: Path) -> None:
    path = tmp_path / "ok.json"
    path.write_text(json.dumps({"drift_trade_block": False}), encoding="utf-8")
    assert is_drift_trade_blocked(path) is False


def test_returns_true_when_drift_trade_block_is_true(tmp_path: Path) -> None:
    path = tmp_path / "blocked.json"
    path.write_text(json.dumps({"drift_trade_block": True}), encoding="utf-8")
    assert is_drift_trade_blocked(path) is True


def test_returns_false_when_key_is_missing(tmp_path: Path) -> None:
    path = tmp_path / "empty.json"
    path.write_text(json.dumps({}), encoding="utf-8")
    assert is_drift_trade_blocked(path) is False


def test_accepts_string_path(tmp_path: Path) -> None:
    path = tmp_path / "str_path.json"
    path.write_text(json.dumps({"drift_trade_block": True}), encoding="utf-8")
    assert is_drift_trade_blocked(str(path)) is True

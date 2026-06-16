from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from auto_trader.worker.cli import _build_parser, _resolve_risk_limits


def test_build_parser_defaults_worker_order_modes_to_market(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("TREND_ORDER_MODE", raising=False)
    monkeypatch.delenv("RANGE_ORDER_MODE", raising=False)
    monkeypatch.delenv("WORKER_EXECUTION_MODE", raising=False)

    parser = _build_parser()
    args = parser.parse_args([])

    assert args.execution_mode == "testnet"
    assert args.runtime_state_max_age_sec == 120
    assert args.allow_runtime_state_fail_open is False
    assert args.trend_order_mode == "market"
    assert args.range_order_mode == "market"


def test_resolve_risk_limits_uses_production_defaults_without_settings(
    tmp_path: Path,
) -> None:
    symbol, portfolio = _resolve_risk_limits(
        execution_mode="production",
        settings_path="",
        max_symbol_exposure_pct=None,
        max_portfolio_exposure_pct=None,
    )

    assert symbol == 8.0
    assert portfolio == 25.0


def test_resolve_risk_limits_prefers_settings_file_over_defaults(tmp_path: Path) -> None:
    settings_path = tmp_path / "config.prod.yaml"
    settings_path.write_text(
        "\n".join(
            [
                "risk:",
                "  max_symbol_exposure_pct: 8.0",
                "  max_portfolio_exposure_pct: 25.0",
                "",
            ]
        ),
        encoding="utf-8",
    )

    symbol, portfolio = _resolve_risk_limits(
        execution_mode="testnet",
        settings_path=str(settings_path),
        max_symbol_exposure_pct=None,
        max_portfolio_exposure_pct=None,
    )

    assert symbol == 8.0
    assert portfolio == 25.0

from __future__ import annotations

from pathlib import Path

from auto_trader.analysis.weekly_core_feedback import (
    build_weekly_core_feedback,
    write_weekly_core_feedback,
)


def test_build_weekly_core_feedback_unions_core_into_weekly_defaults(tmp_path: Path) -> None:
    weekly_script = tmp_path / "weekly_strategy_revalidation.sh"
    weekly_script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                'export SYMBOLS="${SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT,ADAUSDT}"',
                'export RANGE_ENABLED_SYMBOLS="${RANGE_ENABLED_SYMBOLS:-SOLUSDT,XRPUSDT}"',
                'export TREND_ENABLED_SYMBOLS="${TREND_ENABLED_SYMBOLS:-ETHUSDT,XRPUSDT,ADAUSDT}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    report = {
        "rows": [
            {
                "symbol": "SUIUSDT",
                "strategy": "trend",
                "timeframe": "15m",
                "candidate_status": "core",
            },
            {
                "symbol": "TAOUSDT",
                "strategy": "trend",
                "timeframe": "15m",
                "candidate_status": "core",
            },
            {
                "symbol": "ENAUSDT",
                "strategy": "trend",
                "timeframe": "15m",
                "candidate_status": "core",
            },
        ],
    }

    feedback = build_weekly_core_feedback(report, weekly_script_path=weekly_script)

    assert feedback["baseline"]["symbols"] == [
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "XRPUSDT",
        "BNBUSDT",
        "ADAUSDT",
    ]
    assert feedback["updated"]["symbols"] == [
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "XRPUSDT",
        "BNBUSDT",
        "ADAUSDT",
        "SUIUSDT",
        "TAOUSDT",
        "ENAUSDT",
    ]
    assert feedback["updated"]["trend_enabled_symbols"] == [
        "ETHUSDT",
        "XRPUSDT",
        "ADAUSDT",
        "SUIUSDT",
        "TAOUSDT",
        "ENAUSDT",
    ]
    assert feedback["updated"]["range_enabled_symbols"] == ["SOLUSDT", "XRPUSDT"]
    assert len(feedback["core"]["trade_routes"]) == 3
    assert feedback["route_summary"]["core"] == 3


def test_write_weekly_core_feedback_writes_env_and_markdown(tmp_path: Path) -> None:
    weekly_script = tmp_path / "weekly_strategy_revalidation.sh"
    weekly_script.write_text(
        "\n".join(
            [
                'export SYMBOLS="${SYMBOLS:-BTCUSDT,ETHUSDT}"',
                'export RANGE_ENABLED_SYMBOLS="${RANGE_ENABLED_SYMBOLS:-SOLUSDT}"',
                'export TREND_ENABLED_SYMBOLS="${TREND_ENABLED_SYMBOLS:-ETHUSDT}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    report = {
        "rows": [
            {
                "symbol": "SUIUSDT",
                "strategy": "trend",
                "timeframe": "15m",
                "candidate_status": "core",
            },
            {
                "symbol": "SUIUSDT",
                "strategy": "range",
                "timeframe": "15m",
                "candidate_status": "watchlist",
            },
        ],
    }

    json_path = tmp_path / "weekly_core_feedback.json"
    env_path = tmp_path / "weekly_core_feedback.env"
    md_path = tmp_path / "weekly_core_feedback.md"
    feedback = write_weekly_core_feedback(
        report,
        weekly_script_path=weekly_script,
        json_path=json_path,
        env_path=env_path,
        md_path=md_path,
    )

    assert json_path.exists()
    assert env_path.exists()
    assert md_path.exists()
    env_text = env_path.read_text(encoding="utf-8")
    assert "SYMBOLS=BTCUSDT,ETHUSDT,SUIUSDT" in env_text
    assert "TREND_ENABLED_SYMBOLS=ETHUSDT,SUIUSDT" in env_text
    assert "RANGE_ENABLED_SYMBOLS=SOLUSDT" in env_text
    assert feedback["updated"]["symbols"] == ["BTCUSDT", "ETHUSDT", "SUIUSDT"]
    assert feedback["shadow_routes"][0]["strategy"] == "range"

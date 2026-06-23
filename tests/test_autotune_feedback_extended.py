from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from auto_trader.analysis.autotune_feedback import (
    _unique,
    build_autotune_feedback,
    extract_effective_params,
    load_summary,
    parse_config_label,
    render_env,
    render_markdown,
    write_autotune_feedback,
)


def test_load_summary_reads_json(tmp_path: Path) -> None:
    path = tmp_path / "summary.json"
    path.write_text(json.dumps({"key": "value"}), encoding="utf-8")
    assert load_summary(path) == {"key": "value"}


def test_load_summary_returns_empty_for_non_dict(tmp_path: Path) -> None:
    path = tmp_path / "summary.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert load_summary(path) == {}


def test_parse_config_label_hold_range() -> None:
    result = parse_config_label("hold", "range_hold48")
    assert result == {"range_max_hold_bars": 48}


def test_parse_config_label_hold_trend() -> None:
    result = parse_config_label("hold", "trend_hold72")
    assert result == {"trend_max_hold_bars": 72}


def test_parse_config_label_hold_non_digit() -> None:
    result = parse_config_label("hold", "range_holdXYZ")
    assert result == {}


def test_parse_config_label_trend_next_step() -> None:
    result = parse_config_label("trend_next_step", "cooldown5_exit0.03")
    assert result == {
        "trend_reentry_cooldown_bars": 5,
        "trend_efficiency_exit_threshold": 0.03,
    }


def test_parse_config_label_trend_next_step_no_match() -> None:
    result = parse_config_label("trend_next_step", "invalid_format")
    assert result == {}


def test_parse_config_label_trend_entry_threshold() -> None:
    result = parse_config_label(
        "trend_entry_threshold",
        "cooldown3_exit0.02_breakout0.5_momentum0.4_pullback0.3_higherhigh0.6",
    )
    assert result == {
        "trend_reentry_cooldown_bars": 3,
        "trend_efficiency_exit_threshold": 0.02,
        "trend_breakout_persistence_min": 0.5,
        "trend_momentum_persistence_min": 0.4,
        "trend_pullback_shallowness_min": 0.3,
        "trend_higher_high_persistence_min": 0.6,
    }


def test_parse_config_label_trend_entry_threshold_no_match() -> None:
    result = parse_config_label("trend_entry_threshold", "bad_label")
    assert result == {}


def test_parse_config_label_range_matrix() -> None:
    result = parse_config_label("range_matrix", "wick0.3_reversaltrue_cooldown5")
    assert result == {
        "range_wick_ratio_min": 0.3,
        "range_require_reversal_candle": True,
        "range_reentry_cooldown_bars": 5,
    }


def test_parse_config_label_range_matrix_reversal_false() -> None:
    result = parse_config_label("range_matrix", "wick0.2_reversalfalse_cooldown3")
    assert result["range_require_reversal_candle"] is False


def test_parse_config_label_range_matrix_no_match() -> None:
    result = parse_config_label("range_matrix", "invalid")
    assert result == {}


def test_parse_config_label_regime_threshold() -> None:
    result = parse_config_label("regime_threshold", "adx25_breakouthold2_regimehold1_hvcool5")
    assert result == {
        "regime_trend_adx_threshold": 25.0,
        "regime_trend_breakout_persistence_min_bars": 2,
        "min_regime_hold_bars": 1,
        "high_vol_cooldown_bars": 5,
    }


def test_parse_config_label_regime_threshold_no_match() -> None:
    result = parse_config_label("regime_threshold", "unknown")
    assert result == {}


def test_parse_config_label_unknown_stage() -> None:
    result = parse_config_label("unknown_stage", "anything")
    assert result == {}


def test_extract_effective_params_walks_stages() -> None:
    route_summary: dict[str, Any] = {
        "selected_stage": "trend_next_step",
        "stages": [
            {
                "stage": "hold",
                "best": {"config_label": "trend_hold48"},
            },
            {
                "stage": "trend_next_step",
                "best": {"config_label": "cooldown5_exit0.03"},
            },
        ],
    }
    params = extract_effective_params(route_summary)
    assert params["trend_max_hold_bars"] == 48
    assert params["trend_reentry_cooldown_bars"] == 5
    assert params["trend_efficiency_exit_threshold"] == 0.03


def test_extract_effective_params_stops_at_selected_stage() -> None:
    route_summary: dict[str, Any] = {
        "selected_stage": "hold",
        "stages": [
            {"stage": "hold", "best": {"config_label": "range_hold24"}},
            {"stage": "range_matrix", "best": {"config_label": "wick0.3_reversaltrue_cooldown5"}},
        ],
    }
    params = extract_effective_params(route_summary)
    assert "range_max_hold_bars" in params
    assert "range_wick_ratio_min" not in params


def test_extract_effective_params_handles_missing_stages() -> None:
    route_summary: dict[str, Any] = {"selected_stage": "hold"}
    params = extract_effective_params(route_summary)
    assert params == {}


def test_extract_effective_params_handles_non_list_stages() -> None:
    route_summary: dict[str, Any] = {"selected_stage": "hold", "stages": "invalid"}
    params = extract_effective_params(route_summary)
    assert params == {}


def test_extract_effective_params_handles_non_dict_best() -> None:
    route_summary: dict[str, Any] = {
        "selected_stage": "hold",
        "stages": [{"stage": "hold", "best": "not_a_dict"}],
    }
    params = extract_effective_params(route_summary)
    assert params == {}


def test_render_env_generates_env_lines() -> None:
    feedback: dict[str, Any] = {
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "trend_enabled_symbols": ["BTCUSDT"],
        "range_enabled_symbols": ["ETHUSDT"],
        "trade_routes": [
            {"route_key": "trend:BTCUSDT:1h", "selected_stage": "hold"},
            {"route_key": "range:ETHUSDT:30m", "selected_stage": "range_matrix"},
        ],
    }
    env_text = render_env(feedback)
    assert "SYMBOLS=BTCUSDT,ETHUSDT" in env_text
    assert "TREND_ENABLED_SYMBOLS=BTCUSDT" in env_text
    assert "RANGE_ENABLED_SYMBOLS=ETHUSDT" in env_text
    assert "CORE_ROUTE_1_KEY=trend:BTCUSDT:1h" in env_text
    assert "CORE_ROUTE_2_KEY=range:ETHUSDT:30m" in env_text


def test_render_env_skips_non_dict_routes() -> None:
    feedback: dict[str, Any] = {
        "symbols": [],
        "trend_enabled_symbols": [],
        "range_enabled_symbols": [],
        "trade_routes": ["not_a_dict"],
    }
    env_text = render_env(feedback)
    assert "CORE_ROUTE" not in env_text


def test_render_markdown_includes_route_table() -> None:
    feedback: dict[str, Any] = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "summary_path": "test.json",
        "source_out_dir": "out",
        "selection_mode": "expansion",
        "route_count": 1,
        "symbols": ["BTCUSDT"],
        "trend_enabled_symbols": ["BTCUSDT"],
        "range_enabled_symbols": [],
        "trade_routes": [
            {
                "route_key": "trend:BTCUSDT:1h",
                "selected_stage": "hold",
                "pf_mean": 1.5,
                "expectancy_bps_mean": 10.0,
                "period_pnl_mean": 5.0,
                "max_dd_mean": 0.003,
                "closed_trades_mean": 20.0,
                "params": {"trend_max_hold_bars": 48},
            }
        ],
    }
    md = render_markdown(feedback)
    assert "trend:BTCUSDT:1h" in md
    assert "trend_max_hold_bars=48" in md


def test_safe_float_returns_zero_for_invalid() -> None:
    from auto_trader.utils import safe_float

    assert safe_float("not_a_number") == 0.0
    assert safe_float(None) == 0.0
    assert safe_float(42) == 42.0


def test_unique_deduplicates_and_uppercases() -> None:
    assert _unique(["btc", "eth", "BTC", "eth"]) == ["BTC", "ETH"]


def test_unique_strips_whitespace() -> None:
    assert _unique([" btc ", " ETH"]) == ["BTC", "ETH"]


def test_unique_skips_empty() -> None:
    assert _unique(["", " ", "btc"]) == ["BTC"]


def test_build_autotune_feedback_with_dict_input() -> None:
    summary: dict[str, Any] = {
        "selection_mode": "expansion",
        "route_summaries": [
            {
                "route": "range:ETHUSDT:30m",
                "selected_stage": "range_matrix",
                "final_state": "core_confirmed",
                "selected": {
                    "candidate_status": "core",
                    "config_label": "wick0.3_reversaltrue_cooldown5",
                    "pf_mean": 1.5,
                    "expectancy_bps_mean": 10.0,
                    "period_pnl_mean": 5.0,
                    "max_dd_mean": 0.003,
                    "closed_trades_mean": 20.0,
                },
                "stages": [
                    {
                        "stage": "range_matrix",
                        "best": {"config_label": "wick0.3_reversaltrue_cooldown5"},
                    }
                ],
            }
        ],
    }
    feedback = build_autotune_feedback(summary)
    assert feedback["route_count"] == 1
    assert "ETHUSDT" in feedback["range_enabled_symbols"]
    assert feedback["summary_path"] == ""


def test_build_autotune_feedback_skips_invalid_route_key() -> None:
    summary: dict[str, Any] = {
        "route_summaries": [
            {
                "route": "invalid_no_colon",
                "final_state": "core_confirmed",
                "selected": {},
            }
        ],
    }
    feedback = build_autotune_feedback(summary)
    assert feedback["route_count"] == 0


def test_build_autotune_feedback_skips_non_confirmed() -> None:
    summary: dict[str, Any] = {
        "route_summaries": [
            {
                "route": "trend:BTCUSDT:1h",
                "final_state": "dropped",
                "selected": {},
            }
        ],
    }
    feedback = build_autotune_feedback(summary)
    assert feedback["route_count"] == 0


def test_write_autotune_feedback_writes_all_artifacts(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "selection_mode": "expansion",
                "baseline_candidate_report": str(tmp_path / "nonexistent_baseline.json"),
                "route_summaries": [
                    {
                        "route": "trend:BTCUSDT:1h",
                        "selected_stage": "hold",
                        "final_state": "core_confirmed",
                        "selected": {
                            "candidate_status": "core",
                            "config_label": "trend_hold48",
                            "pf_mean": 1.5,
                        },
                        "stages": [{"stage": "hold", "best": {"config_label": "trend_hold48"}}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    out_dir = tmp_path / "out"
    feedback = write_autotune_feedback(
        summary_path,
        json_path=out_dir / "feedback.json",
        env_path=out_dir / "feedback.env",
        md_path=out_dir / "feedback.md",
        manifest_json_path=out_dir / "manifest.json",
        manifest_md_path=out_dir / "manifest.md",
        full_manifest_json_path=out_dir / "full_manifest.json",
        full_manifest_md_path=out_dir / "full_manifest.md",
    )

    assert feedback["route_count"] == 1
    assert (out_dir / "feedback.json").exists()
    assert (out_dir / "feedback.env").exists()
    assert (out_dir / "feedback.md").exists()
    assert (out_dir / "manifest.json").exists()
    assert (out_dir / "manifest.md").exists()
    assert (out_dir / "full_manifest.json").exists()
    assert (out_dir / "full_manifest.md").exists()

    env_content = (out_dir / "feedback.env").read_text(encoding="utf-8")
    assert "BTCUSDT" in env_content

    md_content = (out_dir / "feedback.md").read_text(encoding="utf-8")
    assert "trend:BTCUSDT:1h" in md_content

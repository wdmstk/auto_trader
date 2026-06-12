from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pandas as pd


def test_timeframe_comparison_results_list_builds_route_state_table(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    summary_path = tmp_path / "timeframe_comparison_summary.json"
    candidate_report_path = tmp_path / "candidate_report.json"
    out_path = tmp_path / "timeframe_comparison_result_list.md"
    data_root = tmp_path / "run_data"
    (data_root / "signals").mkdir(parents=True)
    (data_root / "analysis").mkdir(parents=True)

    summary_path.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "symbol": "ETHUSDT",
                        "strategy": "trend",
                        "timeframe": "15m",
                        "pf_mean": 1.23,
                        "expectancy_bps_mean": 4.5,
                        "period_pnl_mean": 1.1,
                        "max_dd_mean": 0.02,
                        "closed_trades_mean": 8.0,
                    }
                ]
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    candidate_report_path.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "symbol": "ETHUSDT",
                        "strategy": "trend",
                        "timeframe": "15m",
                        "candidate_status": "probe",
                        "candidate_score": 2.5,
                    }
                ]
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    pd.DataFrame(
        [
            {
                "entry_signal": False,
                "add_signal": False,
                "signal_reason_codes": ["TR_BLOCK_SYMBOL_DISABLED"],
            },
            {
                "entry_signal": False,
                "add_signal": False,
                "signal_reason_codes": ["TR_BLOCK_SYMBOL_DISABLED"],
            },
        ]
    ).to_parquet(data_root / "signals" / "ETHUSDT_15m_trend_signals.parquet")
    pd.DataFrame([{"closed_trades": 0.0}, {"closed_trades": 2.0}]).to_parquet(
        data_root / "analysis" / "walkforward_ETHUSDT_15m_trend_summary.parquet"
    )

    subprocess.run(
        [
            "bash",
            "./scripts/timeframe_comparison_results_list.sh",
        ],
        cwd=root,
        env={
            **os.environ,
            "SUMMARY_PATH": str(summary_path),
            "CANDIDATE_REPORT_PATH": str(candidate_report_path),
            "OUT_PATH": str(out_path),
            "DATA_ROOT": str(data_root),
        },
        check=True,
    )

    output = out_path.read_text(encoding="utf-8")
    assert "candidate_status_counts: probe=1" in output
    expected_row = (
        "| trend | ETHUSDT | probe | blocked | yes | no | 0 | 2.00 | 1.230 | 4.50 | "
        "1.100 | 0.02000 | 8.00 | 2.50 |"
    )
    assert expected_row in output

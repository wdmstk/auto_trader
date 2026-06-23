# auto_trader

暗号資産FXの**Regime-based自動売買システム**です。
目的は短期的な見た目の成績ではなく、長期生存・DD制御・運用安全性です。

## プロジェクト方針

- `regime first`
- `risk first`
- `execution safety first`
- `observability first`
- `prediction last`

詳細方針:
- ベース方針: `base_policy.md`
- 開発ルール: `PROJECT_RULES.md`
- エージェント方針: `AGENT.md`

## AI開発ワークスペースドキュメント

このプロジェクトは、AIを活用した開発を円滑にするために、以下のドキュメント群を提供します。

*   `AGENTS.md`: AIエージェントの責任とプロジェクトの進化に関するガイドライン。
*   `TASKS.md`: 現在の作業、バックログ、技術的負債、将来のアイデアを整理したタスクリスト。
*   `ROADMAP.md`: プロジェクトの現在のステージ、次のマイルストーン、長期ビジョン、依存関係、リスク、将来の機能を示すロードマップ。
*   `ARCHITECTURE.md`: 全体的なアーキテクチャ、ディレクトリ/レイヤーの責任、依存関係フロー、設計原則、パターン、アンチパターン、将来のスケーラビリティ。
*   `CHANGELOG.md`: プロジェクトの変更履歴。
*   `DECISIONS.md`: 重要なアーキテクチャ上の決定とその理由をまとめたドキュメント。
*   `.clinerules/`: コード品質、アーキテクチャ、テスト、セキュリティ、ドキュメンテーション、Git、パフォーマンス、リファクタリング、レビューに関するAI指示を含むモジュール化されたルールファイル。
*   `workflows/`: 機能開発、バグ修正、リファクタリング、リリース、ドキュメンテーション、テストに関する標準化されたワークフロー定義。

## 現在の実装ステータス

Phase 0-29 の主要運用機能まで実装済み:
- `pyproject.toml` によるPythonプロジェクト基盤
- 品質ゲート: `ruff` / `mypy` / `pytest` / `pre-commit`
- 設定ローダ（`config.<env>.yaml` + 環境変数上書き）
- `prod` 実行時のAPIキー必須ガード
- 構造化ログ（JSON Lines）基盤
- Runtime gate / Dry-run orchestrator / E2E smoke / Futures testnet 接続
- state durability（atomic write + lock + backup recovery）
- Runtime metrics health check / longrun evidence / Go-Live checklist auto update
- timeframe policy（`15m(regime) + 5m(signal) + 1m(execution)`）評価導線
- range/trend の symbol gating + cooldown + entry score 導線
- 週次戦略再評価ジョブ（定期実行は `./scripts/weekly_strategy_revalidation_with_core.sh`、手動本線は `./scripts/weekly_strategy_revalidation.sh`）

Phase 26-29（drift検知 / 指値最適化 / ボラ加重エクスポージャー / chaos test拡張）は
実装済みで、Spec/Review/Checklist を軸に継続調整します。

## ドキュメント構成

`docs/` は ADR（意思決定）と Spec（実装仕様）を分離しています。

- 運用ガイド: `docs/README.md`
- ADR:
  - `docs/adr/0001-regime-risk-first-principles.md`
  - `docs/adr/0002-operational-safety-and-deployment-gates.md`
  - `docs/adr/0003-ml-as-entry-filter-not-price-predictor.md`
- Spec:
  - `docs/specs/phase0-development-foundation-spec.md`
  - `docs/specs/phase1-data-infrastructure-spec.md`
  - `docs/specs/phase2-feature-engine-spec.md`
  - `docs/specs/phase3-regime-classifier-spec.md`
- 実装補助:
  - `docs/implementation/phase0-3-implementation-checklist.md`
  - `docs/implementation/phase25plus-standard-operations.md`
  - `docs/implementation/test-strategy-phase0-3.md`
  - `docs/implementation/risk-register-phase0-3.md`
  - `docs/implementation/futures-testnet-operations.md`
  - `docs/implementation/trading-go-live-checklist.md`
  - `docs/implementation/add-policy-adoption-plan.md`
  - `docs/implementation/phase26-implementation-checklist.md`
  - `docs/implementation/phase27-implementation-checklist.md`
  - `docs/implementation/phase28-implementation-checklist.md`
  - `docs/implementation/phase29-implementation-checklist.md`

## セットアップ

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

## 品質チェック

```bash
ruff check .
mypy src

# smoke（高速）
pytest -q -m smoke

# full（回帰全体）
pytest -q
PRE_COMMIT_HOME=.cache/pre-commit pre-commit run --all-files
```

## CI

- GitHub Actions: `.github/workflows/ci.yml`
- `full`: `ruff / mypy / pytest -q`
- `smoke`: `pytest -q -m smoke`
- `nightly`: 毎日 UTC 18:00（JST 03:00）に full/smoke を自動実行
- 成果物: `smoke-report.xml`, `full-report.xml` を artifact 保存

required checks 検証:
```bash
.venv/bin/python scripts/validate_required_checks.py
```

CIでは `validate-gates` ジョブが同検証を自動実行します。

## 設定ファイル

- `config/config.local.yaml`
- `config/config.ci.yaml`
- `config/config.prod.yaml`

`prod` モードでは以下の環境変数が必須です。

- `BINANCE_API_KEY`
- `BINANCE_API_SECRET`

## Runtime制御イベント反映

GUIの操作イベント（`data/gui/control_events.jsonl`）を runtime state に反映します。

```bash
# 1回処理
python -m auto_trader.runtime

# 監視モード（2秒間隔）
python -m auto_trader.runtime --watch --interval-sec 2
```

補足（Durability）:
- state 書き込みは `atomic write + lock + backup recovery` を適用済みです。
- 対象: `positions.parquet`, `gateway_state.json`, `runtime/control_state.json`, `ops/notify_state.json`

長時間連続運転の実証:
- `docs/implementation/longrun-validation-playbook.md`
- `docs/implementation/longrun-validation-record-2026-05-31.md`（初回証跡）

## Opsアラート評価

```bash
python -m auto_trader.ops \
  --runtime-state-path data/runtime/control_state.json \
  --risk-eval-path data/risk/risk_eval.parquet

# 永続化（parquet/jsonl）
python -m auto_trader.ops \
  --runtime-state-path data/runtime/control_state.json \
  --risk-eval-path data/risk/risk_eval.parquet \
  --output-dir data/ops

# 監視モード（5秒間隔で評価＋保存）
python -m auto_trader.ops \
  --runtime-state-path data/runtime/control_state.json \
  --risk-eval-path data/risk/risk_eval.parquet \
  --watch --interval-sec 5 --output-dir data/ops

# portfolio risk（相関エクスポージャー含む）評価
python -m auto_trader.risk \
  --input-path data/risk/risk_input.parquet \
  --output-path data/risk/risk_eval.parquet \
  --max-correlated-exposure-pct 50

# NOTE:
# correlated_exposure_pct 列が未存在の場合、同一timestampの
# 上位2銘柄の symbol_exposure_pct 合計で自動推定されます。

# risk_input に correlated_exposure_pct を補完（未列時）
./scripts/enrich_risk_input_with_correlation.sh

# 相関集中ブロックの動作シナリオ確認
./scripts/risk_correlated_exposure_check.sh
```

## 通知チャネル連携（Phase 15）

```bash
python -m auto_trader.notify \
  --alerts-path data/ops/alerts.parquet \
  --output-dir data/ops \
  --webhook-url https://example.com/webhook \
  --warning-to-webhook

# 環境変数から読込 + 疎通試験
cp ops/env/notify.env.example ops/env/notify.env
$EDITOR ops/env/notify.env
set -a
. ops/env/notify.env
set +a
python -m auto_trader.notify --from-env --test-alert

# 常駐監視
python -m auto_trader.notify --from-env --watch --interval-sec 5 --output-dir data/ops
```

`systemctl --user` で常駐させる場合は `ops/systemd/auto-trader-notify.user.service.example` を使います。`systemd` の system service 用テンプレートとは `WantedBy` が異なります。

## E2Eスモーク（Phase 17）

```bash
python -m auto_trader.e2e \
  --signals-path data/signals/BTCUSDT_1m_range_signals.parquet \
  --risk-eval-path data/risk/risk_eval.parquet \
  --runtime-state-path data/runtime/control_state.json \
  --output-dir data/e2e
```

## Exchange CLI（Dry-run / Testnet）

```bash
# dry-run（既定）
python -m auto_trader.exchange \
  --symbol BTCUSDT --side buy --qty 0.001 --pass-filter

# testnet 実送信（優先）
export BINANCE_TESTNET_API_KEY=...
export BINANCE_TESTNET_API_SECRET=...

# testnet-live は BINANCE_TESTNET_* を必須として扱います。
python -m auto_trader.exchange \
  --mode testnet-live \
  --symbol BTCUSDT --side buy --qty 0.001 --pass-filter \
  --runtime-state-path data/runtime/control_state.json \
  --state-path data/exchange/gateway_state.json

# futures testnet 実送信
export BINANCE_FUTURES_TESTNET_API_KEY=...
export BINANCE_FUTURES_TESTNET_API_SECRET=...
python -m auto_trader.exchange \
  --mode testnet-futures-live \
  --symbol BTCUSDT --side buy --qty 0.001 --pass-filter \
  --runtime-state-path data/runtime/control_state.json \
  --state-path data/exchange/gateway_state.json
```

## Preflight Check

```bash
# dry-run前チェック
./scripts/preflight_check.sh dry-run

# spot testnet前チェック
./scripts/preflight_check.sh testnet-live

# futures testnet前チェック
./scripts/preflight_check.sh testnet-futures-live

# production前チェック
./scripts/preflight_check.sh production
```

## Runtime Metrics Monitor

```bash
# 単発取得（stdoutにJSON）
python -m auto_trader.monitor \
  --runtime-state-path data/runtime/control_state.json \
  --gateway-state-path data/exchange/gateway_state.json \
  --risk-eval-path data/risk/risk_eval.parquet \
  --order-events-path data/exchange/order_events.jsonl

# 監視モード（jsonl証跡）
python -m auto_trader.monitor \
  --watch --interval-sec 5 \
  --output-jsonl data/validation/runtime_metrics.jsonl
```

主な確認項目:
- `gateway_pending_orders`（queue backlog）
- `order_latency_p95_ms`（注文遅延）
- `risk_block_count` / `risk_latest_dd_pct` / `risk_latest_exposure_pct`
- `runtime_trading_enabled` / `runtime_emergency_stop`

### Runtime Metrics Health Check

```bash
# runtime_metrics.jsonl をしきい値で自動採点（pass/warn/fail）
./scripts/runtime_metrics_health_check.sh
```

成果物:
- `data/validation/runtime_metrics_health_report.json`

## Futures Runtime Gate Check

```bash
# .env 読込後に実行（futures testnet key が必要）
set -a
source .env
set +a

./scripts/futures_runtime_gate_check.sh
```

成果物:
- `data/validation/futures_runtime_gate_check.jsonl`

## Longrun 8h Check

```bash
# 8h耐久 + checkpoint記録 + runtime metrics自動採点
./scripts/longrun_8h_check.sh
  # (デフォルトで longrun record への自動追記まで実行)

# 追記先を明示する場合（任意）
RECORD_PATH=docs/implementation/longrun-validation-record-2026-06-01.md \
  ./scripts/longrun_8h_check.sh

# longrun本体とは別に、後から手動追記する場合
./scripts/append_longrun_record.sh

# 重複でも強制追記する場合
FORCE_APPEND=true ./scripts/append_longrun_record.sh

# ファイル更新せず、追記内容だけプレビュー
DRY_RUN=true ./scripts/append_longrun_record.sh

# 出力形式を markdown に変更（標準出力に追記ブロックを表示）
OUTPUT_FORMAT=markdown DRY_RUN=true ./scripts/append_longrun_record.sh

# longrun時の自動追記を無効化する場合
ENABLE_APPEND_RECORD=false ./scripts/longrun_8h_check.sh

# Go-Liveチェックリストの判定欄を自動更新
./scripts/update_go_live_checklist.sh

# 反映前プレビュー
DRY_RUN=true ./scripts/update_go_live_checklist.sh
```

補足: 実行後、チェックリスト末尾に `Auto Decision Notes` と `Auto Open Items`（未達理由同期）が自動更新されます。

補足:
- 同一 `checkpoints_window` かつ同一 `checkpoints_rows` の場合は重複追記を自動スキップします。

成果物:
- `data/validation/longrun_checkpoints.jsonl`
- `data/validation/longrun_checkpoints.md`
- `data/validation/runtime_metrics.jsonl`
- `data/validation/runtime_metrics_health_report.json`

終了時サマリ:
- `LONGRUN_SUMMARY overall=GO|CONDITIONAL_GO|NO_GO ...` を標準出力に1行表示

## Strategy Expectation Check (Range/Trend)

```bash
./scripts/strategy_expectation_check.sh
```

成果物:
- `data/validation/strategy_check/summary.json`
- `data/validation/strategy_check/e2e_range/smoke_report.json`
- `data/validation/strategy_check/e2e_trend/smoke_report.json`

## Walkforward Visual Check

```bash
./scripts/walkforward_visual_check.sh
```

成果物:
- `data/analysis/walkforward_<SYMBOL>_<TIMEFRAME>_range_summary.parquet`
- `data/analysis/walkforward_<SYMBOL>_<TIMEFRAME>_trend_summary.parquet`
- `data/analysis/walkforward_<SYMBOL>_<TIMEFRAME>_*_trades.parquet`
- `data/analysis/walkforward_<SYMBOL>_<TIMEFRAME>_*_portfolio.parquet`

GUI:
```bash
streamlit run src/auto_trader/gui/app.py
```
- `Multi-Symbol Panel` で複数銘柄の regime/entry件数に加え、PnL/DD/Exposure・return 相関行列・walkforward 指標（PF/WinRate/DD/PnL）を確認できます。
- `Trading` タブの `Exchange Position Sync` で Binance Futures testnet の現在ポジションと local `positions.parquet` の差分を直接確認できます。

## Parallel Walkforward (Multi-Symbol)

```bash
./scripts/parallel_walkforward.sh
```

環境変数で調整:
```bash
SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT \
STRATEGIES=range,trend \
TIMEFRAME=1m \
FOLDS=4 \
PARALLEL=4 \
./scripts/parallel_walkforward.sh
```

成果物:
- `data/validation/parallel_walkforward_summary.jsonl`

TAT比較（逐次 vs 並列）:
```bash
./scripts/parallel_walkforward_benchmark.sh
```

成果物:
- `data/validation/parallel_walkforward_benchmark.json`

## Prepare Long Window Data (For Visual Validation)

```bash
chmod +x scripts/prepare_long_window_visual_data.sh
./scripts/prepare_long_window_visual_data.sh
```

環境変数で期間調整:
```bash
FROM_TS=2026-01-01T00:00:00+00:00 \
TO_TS=2026-02-01T00:00:00+00:00 \
MIN_REGIME_HOLD_BARS=1 \
HIGH_VOL_COOLDOWN_BARS=1 \
./scripts/prepare_long_window_visual_data.sh
```

## Multi-Symbol Data Pipeline (Phase A)

```bash
./scripts/multi_symbol_data_pipeline.sh
```

環境変数で調整:
```bash
SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT \
FROM_TS=2026-01-01T00:00:00+00:00 \
TO_TS=2026-01-08T00:00:00+00:00 \
RANGE_REQUIRE_REVERSAL_CANDLE=false \
RANGE_WICK_RATIO_MIN=0.3 \
RANGE_REENTRY_COOLDOWN_BARS=2 \
RANGE_ENABLED_SYMBOLS=SOLUSDT,XRPUSDT,BNBUSDT \
TREND_REENTRY_COOLDOWN_BARS=2 \
TREND_ENABLED_SYMBOLS=ETHUSDT,XRPUSDT \
STRICT=false \
./scripts/multi_symbol_data_pipeline.sh
```

成果物:
- `data/validation/multi_symbol_pipeline_summary.jsonl`

## Weekly Strategy Revalidation

```bash
./scripts/weekly_strategy_revalidation_with_core.sh
```

成果物:
- `data/validation/weekly_revalidation/weekly_revalidation_report.json`
- `data/validation/weekly_revalidation/timeframe_comparison_summary.json`
- `data/validation/weekly_revalidation/cost_grid_result.json`

自動売買対象の daily backtest:

```bash
./scripts/backtest_symbol_rotation.sh
```

このスクリプトは `data/validation/weekly_revalidation/weekly_revalidation_report.json` の `selection.trade_routes` を起点に、live の自動売買対象だけを backtest します。

## Dry-Run Orchestrator（Phase 19）

```bash
python -m auto_trader.orchestrator \
  --dry-run \
  --signals-path data/signals/BTCUSDT_1m_range_signals.parquet \
  --risk-eval-path data/risk/risk_eval.parquet \
  --runtime-state-path data/runtime/control_state.json \
  --output-dir data/orchestrator
```

## 次の実装対象

1. Phase 1: Binance OHLCV取得・正規化・Parquet保存
2. Phase 2: 特徴量エンジン
3. Phase 3: Regime分類器（`HIGH_VOL = NO TRADE` 強制）

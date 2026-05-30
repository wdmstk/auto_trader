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

## 現在の実装ステータス

Phase 0（開発基盤）まで実装済み:
- `pyproject.toml` によるPythonプロジェクト基盤
- 品質ゲート: `ruff` / `mypy` / `pytest` / `pre-commit`
- 設定ローダ（`config.<env>.yaml` + 環境変数上書き）
- `prod` 実行時のAPIキー必須ガード
- 構造化ログ（JSON Lines）基盤

Phase 1以降（データ・特徴量・Regime分類）は仕様化済みで順次実装予定です。

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
  - `docs/implementation/test-strategy-phase0-3.md`
  - `docs/implementation/risk-register-phase0-3.md`

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
```

## 通知チャネル連携（Phase 15）

```bash
python -m auto_trader.notify \
  --alerts-path data/ops/alerts.parquet \
  --output-dir data/ops \
  --webhook-url https://example.com/webhook \
  --warning-to-webhook

# 環境変数から読込 + 疎通試験
python -m auto_trader.notify --from-env --test-alert

# 常駐監視
python -m auto_trader.notify --from-env --watch --interval-sec 5 --output-dir data/ops
```

## E2Eスモーク（Phase 17）

```bash
python -m auto_trader.e2e \
  --signals-path data/signals/BTCUSDT_1m_range_signals.parquet \
  --risk-eval-path data/risk/risk_eval.parquet \
  --runtime-state-path data/runtime/control_state.json \
  --output-dir data/e2e
```

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

# Phase 0 Spec: 開発基盤

- Version: 1.0
- Date: 2026-05-30
- Related ADR: 0001, 0002

## 目的
品質と安全性を担保した開発基盤を定義し、実装時の裁量差をなくす。

## 入力（I/O契約）
- `config.<env>.yaml`（`local|ci|prod`）
- 環境変数（機密値のみ）
  - `BINANCE_API_KEY`
  - `BINANCE_API_SECRET`
  - `DISCORD_WEBHOOK_URL`（任意）
  - `TELEGRAM_BOT_TOKEN`（任意）

## 出力（I/O契約）
- 構造化ログイベント（JSON Lines）
  - 必須キー: `ts`, `level`, `event`, `symbol`, `regime`, `order_id`, `trace_id`, `message`
- 品質ゲート結果
  - lint, format, type, test, pre-commit

## 前提条件
- Pythonプロジェクト管理は `pyproject.toml` を単一の真実源とする。
- 静的解析、型検査、テストはCIで必須ゲートとする。
- 機密情報は環境変数経由で注入し、リポジトリに平文保存しない。

## 仕様
1. 品質ゲート
- lint: 失敗時はマージ不可。
- format: 差分ゼロで通過すること。
- type: 時系列・金額計算の型不整合を禁止。
- test: 最低限ユニットテスト必須。
- pre-commit: ローカルで同一基準を実行。

2. 設定レイヤ
- 優先順位: `env var > config.<env>.yaml > default`
- `prod` は明示指定時のみ有効化する。
- 重要パラメータ（risk上限、leverage上限）は未設定時に起動失敗。
- 設定キー契約（最小）
  - `system.env`: `local|ci|prod`
  - `system.mode`: `dry_run|testnet|production`
  - `exchange.name`: `binance`
  - `exchange.margin_type`: `isolated`（固定）
  - `exchange.max_leverage`: `1-3` の整数
  - `risk.max_risk_per_trade_pct`: `0 < x <= 1.0`
  - `risk.max_symbol_exposure_pct`: `0 < x <= 100`
  - `risk.max_portfolio_exposure_pct`: `0 < x <= 100`
  - `risk.max_drawdown_pct`: `0 < x <= 100`
  - `runtime.emergency_stop_enabled`: `true|false`
  - `logging.level`: `DEBUG|INFO|WARN|ERROR`
  - `logging.jsonl_path`: 文字列パス

3. ログ/監視最小要件
- 全注文イベントに `trace_id` と `order_id` を付与。
- エラー分類: `market_data`, `signal`, `risk`, `execution`, `exchange`, `infra`
- 緊急停止発火時は WARN 以上で必ず通知する。

## 失敗モードと対策
- 設定欠落: 起動時バリデーションで即時失敗。
- 機密値未設定: 実発注モードを禁止。
- ログ出力不能: 安全側に倒し、新規発注を停止。

## テスト観点
- 設定優先順位の単体テスト。
- `prod` 起動ガードのテスト。
- ログ必須キー欠落時の検知テスト。
- エラーカテゴリ分類テスト。

# Phase 16 Spec: Notification Operations Rollout

- Version: 1.0
- Date: 2026-05-31
- Related ADR: 0001, 0002

## 目的
Phase 15 で実装した通知機能を本番運用へ安全に投入するため、設定管理・実地疎通試験・常駐実行手順を標準化する。

## 入力（I/O契約）
- アラートソース: `data/ops/alerts.parquet`
- 通知設定: 環境変数（Webhook URL、SMTP情報）
- 実行モード: one-shot / watch
- 運用設定: interval, cooldown, warning配信可否

## 出力（I/O契約）
- 通知送信監査ログ: `data/ops/notifications.jsonl`
- 稼働状態: systemd/cron の実行ステータス
- 疎通試験結果: `channel, success, response_code, error_reason`

## 前提条件
- 秘密情報はコード/ドキュメントへ直書きしない。
- `critical` 通知経路を最優先で有効化する。
- 失敗時は監査ログから必ず再現追跡できること。

## 仕様
1. 設定ロード
- 通知先は環境変数から受け取る。
- 未設定チャネルは無効として扱う（fail-fastしない）。

2. 実地疎通試験
- one-shot 実行で test alert を送信し、各チャネルの `success` を確認する。
- 認証失敗（401/403）は設定エラーとして即時修正対象にする。

3. 常駐運用
- `python -m auto_trader.notify --watch` で定期送信ループを実行する。
- interval は既定5秒、運用で調整可能。
- `max-iterations` をテスト/検証用に提供する。

4. 運用自動化
- systemd サービスと cron の両手順を提供する。
- 障害時は `notifications.jsonl` と service status を一次情報とする。

## 失敗モードと対策
- 認証情報ミス: 起動前チェック + 疎通試験で検知。
- 重複通知過多: cooldown/dedupe を有効化。
- 常駐停止: systemd `Restart=always` で自己復旧。

## テスト観点
- 環境変数から notifier が正しく構成されること。
- watch モードで定期送信が継続されること。
- 疎通試験コマンドで送信結果が取得できること。

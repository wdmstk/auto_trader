# Phase 15 Spec: Notification Channel Integration (Slack/Email/Webhook)

- Version: 1.0
- Date: 2026-05-31
- Related ADR: 0001, 0002

## 目的
Phase 14 のアラートを運用者へ即時通知し、critical時の初動遅延を減らす。

## 入力（I/O契約）
- アラート入力（Phase 14）
  - `alert_code, severity, detected_at, source, summary, action_required`
- 送信先設定
  - Slack: webhook URL, channel label
  - Email: SMTP host/port/from/to
  - Generic Webhook: endpoint URL, headers

## 出力（I/O契約）
- 通知送信結果
  - `channel, alert_code, sent_at, success, response_code, error_reason`
- 通知監査ログ
  - `data/ops/notifications.jsonl`

## 前提条件
- `critical` は最優先通知（即時送信）とする。
- `warning` は抑制（dedupe/rate-limit）を許容する。
- 通知失敗時は silent fail せず監査ログへ必ず残す。

## 仕様
1. チャネル抽象
- `Notifier` インターフェースを定義し、`send(alert)` を統一呼び出し可能にする。
- 実装: `SlackNotifier`, `EmailNotifier`, `WebhookNotifier`。

2. 送信ポリシー
- `critical`: 全有効チャネルへ即時配信。
- `warning`: Webhook優先、Slack/Emailは設定でON/OFF。
- 同一 `alert_code + summary` の再通知は `cooldown_sec` 内で抑制する。

3. テンプレート
- 件名/タイトルに `severity` と `alert_code` を必須表示。
- 本文に `detected_at`, `source`, `action_required` を必須表示。
- `EMERGENCY_ACTIVE` と `RISK_DD_BREACH` は強調テンプレートを使用する。

4. 失敗時挙動
- 単一チャネル失敗時でも他チャネル送信を継続する。
- 連続失敗回数が閾値超過時は `NOTIFY_CHANNEL_DEGRADED` を発報する。
- 認証エラー（401/403）は自動再試行せず即時警告する。

## 失敗モードと対策
- 通知スパム: dedupe key + cooldown + severity別レート制限。
- 通知欠落: 送信監査ログ + 定期ヘルスチェックを導入。
- 誤送信: 宛先ホワイトリストと dry-run モードで事前検証。

## テスト観点
- `critical` が全チャネル送信対象になること。
- `warning` が設定に従って抑制されること。
- 送信失敗時に `success=false` と `error_reason` が記録されること。
- dedupe/cooldown が同一アラート連打を抑制できること。

# Phase 15 実装チェックリスト（通知チャネル連携）

## 実装項目
- [x] 通知抽象インターフェース実装（Notifier）
- [x] Slack通知実装（Webhook）
- [x] Email通知実装（SMTP）
- [x] Generic Webhook通知実装
- [x] severity別送信ポリシー実装（critical/warning）
- [x] dedupe/cooldown実装
- [x] 通知結果監査ログ実装（jsonl）
- [x] 通知失敗時の劣化検知実装（channel degraded）

## Done定義
- [x] criticalが全有効チャネルへ送信される
- [x] warning抑制（rate-limit/cooldown）が機能する
- [x] 単一チャネル失敗で全体停止しない
- [x] 送信結果に success/error_reason が残る
- [x] ユニット/統合テストが通る

## レビュー観点
1. 通知が停止制御（EMERGENCY判断）より遅延しないこと
2. 秘密情報（Webhook URL/SMTP認証）がログへ漏れないこと
3. 通知失敗が可観測で、運用者が追跡できること

# Phase 15 実装チェックリスト（通知チャネル連携）

## 実装項目
- [ ] 通知抽象インターフェース実装（Notifier）
- [ ] Slack通知実装（Webhook）
- [ ] Email通知実装（SMTP）
- [ ] Generic Webhook通知実装
- [ ] severity別送信ポリシー実装（critical/warning）
- [ ] dedupe/cooldown実装
- [ ] 通知結果監査ログ実装（jsonl）
- [ ] 通知失敗時の劣化検知実装（channel degraded）

## Done定義
- [ ] criticalが全有効チャネルへ送信される
- [ ] warning抑制（rate-limit/cooldown）が機能する
- [ ] 単一チャネル失敗で全体停止しない
- [ ] 送信結果に success/error_reason が残る
- [ ] ユニット/統合テストが通る

## レビュー観点
1. 通知が停止制御（EMERGENCY判断）より遅延しないこと
2. 秘密情報（Webhook URL/SMTP認証）がログへ漏れないこと
3. 通知失敗が可観測で、運用者が追跡できること

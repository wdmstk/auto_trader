# Phase 16 実装チェックリスト（Notify Operations Rollout）

## 実装項目
- [x] 環境変数ベース通知設定ローダー実装
- [x] 通知疎通試験コマンド実装（test alert）
- [x] `notify --watch` 実装
- [x] systemd運用テンプレート作成
- [x] cron運用手順作成
- [x] 運用Runbook更新（確認項目/障害切り分け）

## Done定義
- [x] 実環境で test alert が送信成功する
- [x] watch モードが連続稼働する
- [x] service 再起動時に自動復旧する
- [x] 監査ログから失敗原因を追跡できる
- [x] ユニット/統合テストが通る

## 最新証跡
- 2026-06-08: Slack `TEST_ALERT` を実環境へ送信成功
- 2026-06-08: `systemctl --user status auto-trader-notify.service` で `active (running)` を確認
- 2026-06-08: `kill -9` 後に `Scheduled restart job` -> `Started auto-trader-notify.service` を確認
- 2026-06-08: user service 化に伴い `ops/systemd/auto-trader-notify.user.service.example` を追加

## 未完了
- 追加の運用証跡を採る場合は `docs/implementation/notify-operations.md` の `自動復旧確認` を使用する

## レビュー観点
1. 秘密情報がコード/ログへ漏れないこと
2. critical通知の経路が単一障害点になっていないこと
3. 運用担当者が手順だけで再現できること

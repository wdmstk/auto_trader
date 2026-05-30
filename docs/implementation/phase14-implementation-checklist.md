# Phase 14 実装チェックリスト（Operations Runbook + Alerting）

## 実装項目
- [ ] 監視対象メトリクス定義（DD/stale/reject/emergency）
- [ ] アラート閾値定義（warning/critical）
- [ ] Runbook初動手順の整備（停止/復旧/連絡）
- [ ] watcher稼働確認手順（systemd/cron）の整備
- [ ] 障害切り分けフローの整備

## Done定義
- [ ] critical時の停止手順が1ページで完結している
- [ ] warning/criticalで運用者アクションが区別される
- [ ] 復旧条件が定量的に定義されている
- [ ] 手動操作の監査ログ確認手順がある
- [ ] 主要インシデントの訓練シナリオがある

## レビュー観点
1. base_policy.md の「生存優先」に整合していること
2. HIGH_VOL / EMERGENCY の優先順位が崩れていないこと
3. 属人化せず第三者が同じ判断を再現できること

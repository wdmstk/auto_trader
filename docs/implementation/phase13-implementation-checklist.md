# Phase 13 実装チェックリスト（Streamlit GUI）

## 実装項目
- [ ] ダッシュボード主要パネル実装（PnL/Regime/Exposure/Risk/API）
- [ ] 操作ボタン実装（START/STOP/EMERGENCY系）
- [ ] チャートoverlay実装（regime/entry/exit/ml/risk）
- [ ] 操作イベントログ表示実装
- [ ] staleデータ警告実装

## Done定義
- [ ] 緊急ボタンが常時表示される
- [ ] ボタン操作が監査ログに残る
- [ ] HIGH_VOL/EMERGENCYが視覚的に識別できる
- [ ] ユニット/統合テストが通る

## レビュー観点
1. 誤操作を誘発しないUI配置であること
2. 状態遅延が明示されること
3. 運用者が停止判断を即時に行えること

# Phase 11 実装チェックリスト（Position Management）

## 実装項目
- [x] ポジション状態ストア実装
- [x] 平均取得単価更新ロジック実装
- [x] 部分クローズ反映ロジック実装
- [x] add_count管理実装
- [x] symbol/portfolio exposure算出実装
- [x] 異常約定時の安全停止実装

## Done定義
- [x] avg_entry更新がテストで再現する
- [x] add_count上限超過が抑止される
- [x] exposure閾値超過を検知できる
- [x] ユニット/統合テストが通る

## レビュー観点
1. 約定順序の違いで状態破綻しないこと
2. 部分約定の集計漏れがないこと
3. exposure計算が楽観的になっていないこと

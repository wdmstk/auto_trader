# Phase 12 実装チェックリスト（Risk Management）

## 実装項目
- [x] DD監視ロジック実装
- [x] symbol exposure上限判定実装
- [x] portfolio exposure上限判定実装
- [x] concentration score算出実装
- [x] emergency state管理実装
- [x] risk block理由コード出力実装

## Done定義
- [x] DD超過で即時blockできる
- [x] exposure超過で新規/追加を抑止できる
- [x] emergency stateで発注系が停止する
- [x] reason_codes欠損がない
- [x] ユニット/統合テストが通る

## レビュー観点
1. stale指標利用時に安全側へ倒れること
2. block解除条件が明確であること
3. 緊急状態の状態遷移が単純であること

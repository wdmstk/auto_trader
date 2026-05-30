# Phase 10 実装チェックリスト（Exchange Integration）

## 実装項目
- [x] REST実行クライアント実装
- [x] WebSocket受信クライアント実装
- [x] reconnect/retry実装
- [x] 冪等発注キー実装
- [x] reject/partial fill状態遷移実装
- [x] stale signal破棄実装

## Done定義
- [x] 重複発注ゼロを再現テストで確認
- [x] 切断復旧後に状態同期できる
- [x] partial fill を正しく追跡できる
- [x] ユニット/統合テストが通る

## レビュー観点
1. 冪等性が全発注パスで効くこと
2. retry が危険側へ倒れないこと
3. stale signal が実発注されないこと

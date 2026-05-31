# Phase 25 実装チェックリスト（Rate Limit + Error Taxonomy）

## 実装項目
- [x] gateway エラー種別Enum実装
- [x] reason->Enum 変換実装
- [x] rate limit待機戦略実装（retry_after優先）
- [x] backoff/jitter 実装
- [x] gateway テスト追加
- [x] gateway 例外階層（GatewayError系）実装
- [x] reason分類結果を ErrorCode + 例外へ二重マッピング
- [x] PositionStore の atomic write + lock + backup 実装
- [x] gateway 動的state（未約定注文/seen client id）永続化実装
- [x] 破損時のバックアップ復旧実装
- [x] 永続化系ユニットテスト追加（lock/復旧含む）

## Done定義
- [x] 429相当で待機再試行される
- [x] 最終失敗 reason が標準化される
- [x] 既存ゲート判定が維持される
- [x] 競合時に破壊的上書きしない
- [x] 破損ファイルから復旧できる
- [x] ユニットテストが通る

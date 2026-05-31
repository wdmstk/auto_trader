# Phase 25 実装チェックリスト（Rate Limit + Error Taxonomy）

## 実装項目
- [x] gateway エラー種別Enum実装
- [x] reason->Enum 変換実装
- [x] rate limit待機戦略実装（retry_after優先）
- [x] backoff/jitter 実装
- [x] gateway テスト追加

## Done定義
- [x] 429相当で待機再試行される
- [x] 最終失敗 reason が標準化される
- [x] 既存ゲート判定が維持される
- [x] ユニットテストが通る

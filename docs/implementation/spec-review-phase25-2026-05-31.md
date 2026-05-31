# Specレビュー結果（Phase 25）

- Date: 2026-05-31
- Scope: `phase25-gateway-rate-limit-and-error-taxonomy-spec.md`
- Reviewer: Codex

## 結論
Phase 25 は運用上の重要課題（429対応、reason標準化）を直接解消するため妥当。

## 固定事項
1. `retry_after` 優先待機
2. reason の Enum 標準化
3. 既存ゲートロジックの非破壊

## 残留リスク
- IP/Account weight を使った事前スロットリングは次段（State強化と併走）で実装が必要。

## 実装反映ステータス（2026-05-31）
- `src/auto_trader/exchange/errors.py` に ErrorCode Enum を追加済み。
- `src/auto_trader/exchange/gateway.py` に reason分類・retry_after優先待機・backoff/jitter を実装済み。
- 対応テスト: `tests/test_exchange_gateway.py`（rate limit再試行ケース含む）。

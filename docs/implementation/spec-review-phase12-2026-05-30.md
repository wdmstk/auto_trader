# Specレビュー結果（Phase 12）

- Date: 2026-05-30
- Scope: `phase12-risk-management-spec.md`
- Reviewer: Codex

## 結論
Phase 12 は「DD・exposure・緊急停止」を同時管理する最小安全仕様として妥当。

## 固定事項
1. DD優先
- `max_dd_pct` 超過時は即時 `risk_blocked=true`。

2. Exposure優先
- symbol/portfolio上限を独立判定し、理由コードを記録。

3. Emergency優先
- `EMERGENCY_STOP` 時は発注経路を遮断。
- 手動解除まで状態保持できる設計にする。

## 残留リスク
- 相関指標は入力銘柄集合に依存。
- 市場急変時の指標遅延に対する保守設定が必要。

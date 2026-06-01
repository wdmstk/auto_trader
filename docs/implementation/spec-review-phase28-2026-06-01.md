# Specレビュー結果（Phase 28）

- Date: 2026-06-01
- Scope: `docs/specs/phase28-volatility-weighted-exposure-control-spec.md`
- Reviewer: Codex

## 結論
Phase 28 は相関集中時の実損リスクを低減する仕様として妥当。
既存の相関ゲートを残した上で、volatility加重を追加する方針は安全性が高い。

## 固定事項
1. 既存 `max_correlated_exposure_pct` を維持し、新指標を追加する。
2. `risk_contribution_pct` と `vol_weighted_exposure_pct` を運用指標にする。
3. 閾値超過時は block か size縮小のいずれかで安全側へ倒す。

## レビュー指摘（実装前に明確化すべき点）
- block優先か size縮小優先かの適用順序を固定する必要。
- `size_scale` の下限値（最小発注可能サイズとの関係）を定義する必要。
- rolling window 長と更新頻度を明示しないと再現性が下がる。

## 残留リスク
- 急変時に推定相関が不安定化し、過剰縮小/過小縮小の両リスクがある。
- 欠損時の安全側制御が多発すると取引機会が極端に減る可能性。

## 実装着手条件
- 制御優先順位（block vs scale）を仕様に追記する。
- 指標計算の時間窓と欠損時フォールバックを固定する。

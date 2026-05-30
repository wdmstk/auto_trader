# Specレビュー結果（Phase 11）

- Date: 2026-05-30
- Scope: `phase11-position-management-spec.md`
- Reviewer: Codex

## 結論
Phase 11 は、建玉整合・add管理・exposure監視の最低要件を満たす仕様として妥当。

## 固定事項
1. avg_entry更新
- 約定イベントで逐次更新し、部分クローズ時も整合維持。

2. add管理
- add_countを銘柄別で保持し、上限超過を拒否。

3. exposure管理
- symbol/portfolioを毎イベントで再計算し、閾値超過で停止。

## 残留リスク
- 取引所の約定欠落時に状態ズレが発生しうる。
- 高頻度約定時の再計算コスト増大に注意。

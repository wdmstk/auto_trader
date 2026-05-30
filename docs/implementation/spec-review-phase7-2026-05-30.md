# Specレビュー結果（Phase 7）

- Date: 2026-05-30
- Scope: `phase7-ml-pipeline-spec.md`
- Reviewer: Codex

## 結論
Phase 7（ML Pipeline）は「期待値フィルタ用途」に責務を限定し、実装前仕様として妥当。

## 固定事項
1. 目的制約
- MLは発注可否フィルタ用途のみ。
- 方向予測器として使わない。

2. 時系列制約
- splitは時系列順のみ。
- no shuffle/no leakage を必須検証。

3. 再現性
- model_version / feature_version / train_range を成果物に保存。
- 閾値適用で `pass_filter` を決定可能にする。

## 残留リスク
- ラベル不均衡で閾値が不安定化する可能性。
- regime別で性能偏りが出る可能性（分割評価が必要）。

# Specレビュー結果（Phase 8）

- Date: 2026-05-30
- Scope: `phase8-backtesting-spec.md`
- Reviewer: Codex

## 結論
Phase 8（Backtesting）は実装前仕様として、実運用乖離を抑える主要因（fee/slippage/spread/delay）が固定された。

## 固定事項
1. 実行コスト
- fee/slippage/spread を全取引に適用。
- 未適用は失敗扱い。

2. 遅延約定
- シグナル遅延をモデル化し、保守的な約定評価を採用。

3. 運用整合
- `pass_filter=false` は約定対象外。
- HIGH_VOL停止をバックテストでも強制。

## 残留リスク
- slippageモデルの係数は市場状態依存で変動する。
- 板情報未使用のため極端相場では乖離が残る。

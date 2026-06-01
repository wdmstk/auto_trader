# Specレビュー結果（Phase 28）

- Date: 2026-06-01
- Scope: `docs/specs/phase28-volatility-weighted-exposure-control-spec.md`
- Reviewer: Codex

## 結論
Phase 28 は実装まで完了し、仕様意図（相関集中時の損失抑制）と整合している。
既存相関ゲートを維持したまま、volatility加重指標と縮小導線を追加できている。

## 固定事項
1. 既存 `max_correlated_exposure_pct` を維持し、新指標を追加する。
2. `risk_contribution_pct` と `vol_weighted_exposure_pct` を運用指標にする。
3. 閾値超過時は block か size縮小のいずれかで安全側へ倒す。

## 実装結果（2026-06-01）
- `vol_weighted_exposure_pct` / `risk_contribution_pct` / `size_scale` を risk 出力へ追加。
- `RISK_VOL_WEIGHTED_EXPOSURE` / `RISK_VOL_MISSING` 判定を追加。
- 欠損時フォールバックを実装（`missing_vol_ratio >= 0.2` で block、未満は縮小）。
- GUI に `vol_weighted_exposure_pct` / `risk_contribution_pct` / `size_scale` 表示を追加。
- CLI で閾値調整（soft/hard、risk contribution、min scale、missing ratio）を可能化。
- 検証: `pytest -q tests/test_risk_manager.py tests/test_risk_pipeline.py tests/test_gui_state.py` で 15 passed。

## 残留リスク
- ボラ推定が単純指標依存のため、極端な regime 変化で過縮小/過小縮小余地が残る。
- rolling window を明示管理していない入力経路では銘柄間比較の一貫性が崩れる余地がある。

## 次アクション
- weekly revalidation レポートへ vol-weighted 指標推移を追記する。
- 運用閾値（soft/hard, rc）を runbook に固定値として明記する。

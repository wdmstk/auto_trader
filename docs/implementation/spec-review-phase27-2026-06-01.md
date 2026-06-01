# Specレビュー結果（Phase 27）

- Date: 2026-06-01
- Scope: `docs/specs/phase27-limit-order-and-maker-cost-optimization-spec.md`
- Reviewer: Codex

## 結論
Phase 27 は実装完了し、market互換維持のまま limit/maker 評価導線を追加できている。
状態遷移（filled/partial/expired/canceled）と cost-grid の order_mode 比較が動作しており、仕様意図と整合する。

## 固定事項
1. market モードは互換維持し、limit モードを追加する。
2. `filled/partial/expired/canceled` の状態遷移を必須証跡化する。
3. 成果判定は `gross/net/cost` の一貫性で評価する。

## 実装結果（2026-06-01）
- `BacktestConfig` に `order_mode` / `maker_fee_rate` / `taker_fee_rate` を追加。
- limit約定モデル v1 を実装（タッチ時 partial、1bar 滞留で filled、未成立は expired）。
- partial fill の残数量は v1 で `canceled` 固定を実装。
- `timeframe_comparison.sh` / `backtest_cost_grid.sh` に order_mode 導線を追加。
- `cost_grid_result.json` に `order_mode` 次元を反映。
- 検証:
  - `tests/test_backtest_simulator.py` / `tests/test_backtest_pipeline.py` pass
  - `ORDER_MODES=limit ./scripts/backtest_cost_grid.sh` で比較出力確認

## 残留リスク
- 板厚・queue position を未考慮のため、実約定との乖離余地がある。
- maker前提崩壊（taker化率）の監視閾値は運用チューニングが必要。

## 次アクション
- gross/net/cost の一貫性チェックを自動テストで強化する。
- 実板モデル（深さ・滞留）を使う v2 約定モデルを別Issueで拡張する。

# Specレビュー結果（Phase 29）

- Date: 2026-06-01
- Scope: `docs/specs/phase29-chaos-test-expansion-spec.md`
- Reviewer: Codex

## 結論
Phase 29 は実装まで完了し、運用障害に直結する異常系（partial fill / silent stale）の検証導線を追加できている。
既存 stress/e2e を壊さず追加できており、現行運用と整合する。

## 固定事項
1. partial fill の数量整合を最優先で検証する。
2. silent stale は「検知から停止までの遅延」を必須計測する。
3. fail時は原因追跡できる証跡（イベント時系列）を残す。

## 実装結果（2026-06-01）
- `partial_fill_10pct_cancel` シナリオを追加。
- `silent_ws_stale` シナリオを追加。
- `stale_detect_to_stop_latency_sec`（検知→停止遅延）を実装。
- 緊急停止発火フラグ（`emergency_stop_triggered`）を stress 結果へ出力。
- `scripts/chaos_test.sh` を追加し、`data/validation/chaos/` へ証跡を保存。
- 検証:
  - `pytest -q tests/test_stress_scenarios.py` で 4 passed
  - `./scripts/chaos_test.sh` 実行で `status=pass` を確認（遅延 120.0s）

## 残留リスク
- 実取引所のイベント順序ゆらぎ（遅延・欠落）との乖離は残る。
- stale検知条件は固定閾値のため、銘柄/時間足ごとの最適値調整余地がある。

## 次アクション
- chaos summary を weekly/go-live 判定に段階連携する（warn補助判定）。
- silent stale の閾値チューニング基準を runbook 化する。

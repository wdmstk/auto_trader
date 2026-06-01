# Specレビュー結果（Phase 29）

- Date: 2026-06-01
- Scope: `docs/specs/phase29-chaos-test-expansion-spec.md`
- Reviewer: Codex

## 結論
Phase 29 は運用障害に直結するケース（partial fill / silent stale）を補強できるため妥当。
既存stress/e2eを壊さず追加する方針も現行運用と整合する。

## 固定事項
1. partial fill の数量整合を最優先で検証する。
2. silent stale は「検知から停止までの遅延」を必須計測する。
3. fail時は原因追跡できる証跡（イベント時系列）を残す。

## レビュー指摘（実装前に明確化すべき点）
- stale検知遅延の閾値（warn/fail）を秒単位で固定する必要。
- partial fill ケースの標準シナリオ（10% fill + cancel）を基準ケースとして固定する必要。
- emergency stop 発火条件（連続stale回数 or 秒数）を明文化する必要。

## 残留リスク
- シミュレーション再現と実運用イベント順序が一致しない場合、検証漏れが残る。
- 無言切断系は環境依存差が大きく、テストの不安定化余地がある。

## 実装着手条件
- chaosシナリオ定義ファイル（入力・期待状態・判定閾値）を先に作成する。
- 失敗時証跡の保存場所を runbook に固定する。

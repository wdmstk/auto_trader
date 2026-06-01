# Specレビュー結果（Phase 26）

- Date: 2026-06-01
- Scope: `docs/specs/phase26-feature-drift-detection-spec.md`
- Reviewer: Codex

## 結論
Phase 26 は MLOps の運用空白（特徴量ドリフト監視）を埋める仕様として妥当。
`warn/fail` の段階判定と `is_trade_allowed` 連携方針は、安全側運用に整合する。

## 固定事項
1. 一次指標は `PSI` とし、補助指標 `mean_delta_z` / `std_ratio` を併用する。
2. `warn` は継続運用可、`fail` は新規建て抑止を許可する。
3. 判定は既存 gate（regime/risk/runtime）より後段の追加安全層として実装する。

## レビュー指摘（実装前に明確化すべき点）
- 集約判定ルール（feature単位fail件数や比率しきい値）が未定義。
- `unknown`（基準統計欠落）の最終扱い（warn固定か、条件付きfailか）を実装時に固定する必要。
- 監視GUIへの表示粒度（feature別詳細 or 集約のみ）を先に決める必要。

## 残留リスク
- PSI閾値の初期値が過敏/鈍感のいずれかに偏る可能性。
- 学習時と本番で feature 生成条件が微妙にずれると、誤検知が増える。

## 実装着手条件
- baseline統計の保存フォーマットを決める。
- 集約判定式と fail時の block 条件をチェックリストに追記する。

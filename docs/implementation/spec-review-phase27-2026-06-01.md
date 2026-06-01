# Specレビュー結果（Phase 27）

- Date: 2026-06-01
- Scope: `docs/specs/phase27-limit-order-and-maker-cost-optimization-spec.md`
- Reviewer: Codex

## 結論
Phase 27 は「grossは正だがnetが負」の課題に直接対応する仕様として妥当。
market/limit 並行評価を維持している点は、段階導入の安全性に寄与する。

## 固定事項
1. market モードは互換維持し、limit モードを追加する。
2. `filled/partial/expired/canceled` の状態遷移を必須証跡化する。
3. 成果判定は `gross/net/cost` の一貫性で評価する。

## レビュー指摘（実装前に明確化すべき点）
- partial fill の残数量方針（cancel固定か、次バー繰越か）を初期実装で1つに固定する必要。
- limit 約定条件（タッチ判定、板滞留判定）の保守性基準を明文化する必要。
- maker前提崩壊の判定しきい値（taker化率）を数値で固定する必要。

## 残留リスク
- 約定モデルが楽観的すぎると、backtest優位が過大評価される。
- 実運用では板厚・queue position を未考慮だと乖離が残る。

## 実装着手条件
- 約定判定ルールと状態遷移テーブルを先に定義する。
- cost grid に order_mode 次元を追加する。

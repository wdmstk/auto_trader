# Specレビュー結果（Phase 27）

- Date: 2026-06-07
- Scope: `docs/specs/phase27-limit-order-and-maker-cost-optimization-spec.md`
- Reviewer: Codex

## 結論
Phase 27 の limit/maker 導線は、単なる backtest 比較から weekly/candidate report へ評価理由を持ち上げる形で整合した。
market を本線、limit を診断という方針がレポートと GUI の両方で読み取りやすくなった。

## 固定事項
1. `market` は本線判定、`limit` は診断用途として扱う。
2. weekly/candidate report には limit evidence summary を載せる。
3. maker 前提の崩壊は `taker-like` を含む実績で確認する。
4. 週次候補・feedback・worker の採用単位は `route = symbol + strategy + timeframe` とする。
5. `weekly_core_feedback.env` は補助入力であり、route 正本は JSON とする。
6. 同一 symbol の複数 route を後続の live worker / GUI 統合でも維持する。

## 実装結果（2026-06-07）
- candidate report に `limit` 実績の集約を追加。
- weekly revalidation report に `market_reason` / `limit_reason` / `drift_reason` を持つ decision summary を追加。
- route-centric schema を追加し、`route_counts` / `symbol_counts` / shadow route を分離した。
- `selection.trade_routes` は全 core route を保持し、symbol dedupe をやめた。
- `weekly_core_feedback.json` を新設し、`.env` は strategy ごとの symbol 集合へ派生させた。
- position store を route key 基準へ拡張し、legacy schema の後方互換を維持した。

## 残留リスク
- queue aging / GTC 近似 / 銘柄別 profile は未導入のため、limit の現実約定はまだ近似レベル。
- `taker-like` は運用データ蓄積後に閾値調整が必要。
- legacy position file は読めるが、旧 schema を保存し直すと route metadata が付くため初回 migration 後の差分確認が必要。
- live worker / GUI への route-centric schema 統合は後続コミットで検証する。

## 次アクション
- `phase27` の次PR候補として queue aging / GTC 近似 / 銘柄別 profile を段階的に追加する。

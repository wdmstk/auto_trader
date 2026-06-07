# Specレビュー結果（Phase 11）

- Date: 2026-06-07
- Scope: `docs/specs/phase11-position-management-spec.md`
- Reviewer: Codex

## 結論
同一symbolで複数strategy/timeframeを運用するため、positionの識別単位をsymbolからroute keyへ拡張する。
リスク評価ではrouteを分離したまま保持しつつ、symbol exposureを全route合算で評価する。

## 固定事項
1. `route_key = strategy:symbol:timeframe` をpositionの識別子とする。
2. 同一symbolの複数routeは独立して約定・クローズする。
3. symbol exposureは同一symbolの全routeを合算する。
4. 旧schemaは `legacy:<symbol>:15m` として読み込み、破棄しない。

## 実装結果
- PositionState / FillEventへstrategy、timeframe、route_keyを追加。
- PositionManagerをroute key単位の保持・更新へ変更。
- PositionStoreに新schema保存とlegacy schema読込を追加。
- 空position時もschema付きrisk input/evalを生成できるようにした。

## 残留リスク
- legacy routeと新routeが同時に残る移行期間は、運用者が重複positionの有無を確認する必要がある。
- route単位のemergency closeはworker側の統合テストで継続確認する。

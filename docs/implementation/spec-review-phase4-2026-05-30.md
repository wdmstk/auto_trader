# Specレビュー結果（Phase 4）

- Date: 2026-05-30
- Scope: `phase4-label-generation-spec.md`
- Reviewer: Codex

## 結論
Phase 4（Label Generation）の実装前仕様として、I/O契約・リーク防止・timestamp整合が固定された。

## 固定事項
1. ラベル契約
- `1=TP first`, `0=SL first`, 未ヒットは `null`。
- 同一バーでTP/SL両ヒット時は安全側で `SL first`。

2. 時系列整合
- symbol/timeframe単位で `timestamp` 単調増加必須。
- duplicate timestampは禁止。

3. リーク防止
- featuresとlabelsは同一 `(symbol,timeframe,timestamp)` のみ許可。
- 不一致を検知した時点でジョブ失敗。

## 残留リスク
- `max_horizon_bars` が短すぎると `null` ラベルが増える。
- 相場特性でラベル不均衡が増大するため、次Phaseで分布監視が必要。

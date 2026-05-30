# Phase 9 Spec: Stress Testing

- Version: 1.0
- Date: 2026-05-30
- Related ADR: 0001, 0002

## 目的
通常バックテストでは見えづらい極端環境で、戦略・実行・リスク制御の耐性を検証する。

## 入力（I/O契約）
- バックテスト入力データ（OHLCV, signals, ml_filter）
- ストレスシナリオ設定
  - `volatility_multiplier`
  - `spread_multiplier`
  - `liquidity_shock_factor`
  - `api_timeout_rate`

## 出力（I/O契約）
- シナリオ別結果テーブル
  - `scenario_name, PF, MaxDD, MonthlyPnL, failure_count`
- 劣化比較テーブル
  - `baseline_metric, stressed_metric, degradation_pct`

## 前提条件
- baselineバックテストとの差分比較を必須化。
- ストレス環境でも `HIGH_VOL` 停止ルールを維持。
- failure時は停止理由を必ず記録。

## 仕様
1. 必須シナリオ
- 2x volatility
- flash crash
- low liquidity
- spread widening
- API timeout

2. 実行
- 各シナリオで同一期間・同一初期資金を使用。
- 約定不可・タイムアウト発生は `failure_count` に計上。

3. 判定
- MaxDDが許容閾値超過なら失敗。
- catastrophic month相当の急落が出る場合は要改善判定。

## 失敗モードと対策
- シナリオ未適用: baselineとの差分ゼロならテスト失敗。
- failure未記録: 監査不能のため失敗。
- 比較指標不足: PF/DD/MonthlyPnLの3指標は必須。

## テスト観点
- 各シナリオで入力変形が適用されること。
- failure_countが期待通り増減すること。
- baseline 대비劣化率が計算されること。
- HIGH_VOL停止が維持されること。

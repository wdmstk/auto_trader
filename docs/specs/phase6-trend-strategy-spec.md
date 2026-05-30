# Phase 6 Spec: TREND Strategy

- Version: 1.0
- Date: 2026-05-30
- Related ADR: 0001, 0002, 0003

## 目的
TREND相場で継続優位の局面に限定してエントリーし、押し目継続を取りにいく。

## 入力（I/O契約）
- Regime判定テーブル（Phase 3）
  - 必須: `regime`, `is_trade_allowed`, `confidence`
- 特徴量テーブル（Phase 2）
  - 必須: `momentum_persistence`, `breakout_persistence`, `pullback_shallowness`, `higher_high_persistence`, `trend_efficiency`
- リスク判定テーブル
  - 必須: `risk_blocked`

## 出力（I/O契約）
- TREND戦略シグナルテーブル
  - 主キー: `(symbol, timeframe, timestamp)`
  - カラム:
    - `entry_signal`（bool）
    - `exit_signal`（bool）
    - `add_signal`（bool）
    - `signal_reason_codes`（配列）
    - `risk_blocked`（bool）
    - `position_size_ratio`（float）

## 前提条件
- `regime == TREND` かつ `is_trade_allowed == true` 以外では新規エントリー禁止。
- `HIGH_VOL` 時はTREND戦略を必ず停止。
- 追加ポジション（add/pyramid）は含み益時のみ許可する。

## 仕様
1. エントリー条件（初期）
- `breakout_persistence` が閾値以上
- `momentum_persistence` が閾値以上
- `pullback_shallowness` が閾値以上
- `higher_high_persistence` が閾値以上

2. エグジット条件（初期）
- `regime != TREND`
- トレンド効率低下（`trend_efficiency` 下振れ）
- 急変動検知（high vol遷移）

3. Pyramid条件（初期）
- 既存ポジションが含み益
- `risk_blocked=false`
- add回数上限内

4. 可観測性
- `signal_reason_codes` は必須
- 最低コード:
  - `TR_ENTRY_BREAKOUT_PERSIST`
  - `TR_ENTRY_MOMENTUM_PERSIST`
  - `TR_ENTRY_PULLBACK_SHALLOW`
  - `TR_ENTRY_HIGHER_HIGH`
  - `TR_ADD_IN_PROFIT`
  - `TR_EXIT_REGIME_CHANGED`
  - `TR_EXIT_TREND_WEAKENED`
  - `TR_BLOCK_RISK_LIMIT`
  - `TR_BLOCK_HIGH_VOL`

## 失敗モードと対策
- TREND以外でentry発火: Regime gate違反として失敗。
- add暴走: add回数上限とrisk gateを必須化。
- high vol誤追従: `TR_BLOCK_HIGH_VOL` を最優先適用。

## テスト観点
- TREND時のみentryが立つこと。
- HIGH_VOL時にentry/add停止すること。
- risk_blocked時にentry/addが抑止されること。
- reason_codesが必ず出力されること。

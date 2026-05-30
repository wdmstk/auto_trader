# Phase 5 Spec: RANGE Strategy

- Version: 1.0
- Date: 2026-05-30
- Related ADR: 0001, 0002, 0003

## 目的
RANGE相場で平均回帰優位の局面に限定してエントリーし、低DDで安定した期待値を狙う。

## 入力（I/O契約）
- Regime判定テーブル（Phase 3）
  - 必須: `regime`, `is_trade_allowed`, `confidence`
- 特徴量テーブル（Phase 2）
  - 必須: `rsi`, `bb_width`, `wick_ratio`, `mean_reversion_distance`, `reversal_candle_flag`
- ラベル/評価テーブル（Phase 4）

## 出力（I/O契約）
- RANGE戦略シグナルテーブル
  - 主キー: `(symbol, timeframe, timestamp)`
  - カラム:
    - `entry_signal`（bool）
    - `exit_signal`（bool）
    - `signal_reason_codes`（配列）
    - `risk_blocked`（bool）
    - `position_size_ratio`（float）

## 前提条件
- `regime == RANGE` かつ `is_trade_allowed == true` 以外では新規エントリー禁止。
- `HIGH_VOL` 時はRANGE戦略を必ず停止。
- エントリー根拠は説明可能なルールベースで残す。

## 仕様
1. エントリー条件（初期）
- `rsi` が 40-50 帯で反発方向
- `wick_ratio` が閾値以上（下ヒゲ優位）
- `mean_reversion_distance` が負側からの戻り
- `reversal_candle_flag == 1`

2. エグジット条件（初期）
- `mean_reversion_distance` が中立付近へ回帰
- モメンタム鈍化（補助指標）
- `regime` が `RANGE` 以外へ遷移

3. リスク制御
- symbol/portfolioの上限超過時は `risk_blocked=true`
- `risk_blocked=true` の行は `entry_signal=false` 強制
- `position_size_ratio` は上限内でのみ算出

4. 可観測性
- `signal_reason_codes` は必須
- 最低コード:
  - `RG_ENTRY_RSI_REBOUND`
  - `RG_ENTRY_WICK_CONFIRM`
  - `RG_ENTRY_REVERSAL_CANDLE`
  - `RG_EXIT_MEAN_REVERTED`
  - `RG_EXIT_REGIME_CHANGED`
  - `RG_BLOCK_RISK_LIMIT`
  - `RG_BLOCK_HIGH_VOL`

## 失敗モードと対策
- Regime不整合: RANGE以外でentry発火したら失敗。
- 過剰シグナル: 閾値再調整とウォークフォワード再評価。
- リスク超過見逃し: `risk_blocked` を監視必須項目にする。

## テスト観点
- RANGE時のみentryが立つこと。
- HIGH_VOL時にentry停止すること。
- risk_blocked時にentryが抑止されること。
- reason_codesが必ず出力されること。

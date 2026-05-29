# Phase 2 Spec: 特徴量エンジン

- Version: 1.0
- Date: 2026-05-30
- Related ADR: 0001, 0003

## 目的
Regime判定と戦略判定に必要な特徴量を、リークなし・再現可能な形で生成する。

## 入力（I/O契約）
- 正規化OHLCVテーブル（Phase 1出力）
- 特徴量設定
  - `window`（例: RSI 14, ATR 14, BB 20）
  - `min_history_bars`

## 出力（I/O契約）
- 特徴量テーブル（Parquet）
  - 主キー: `(symbol, timeframe, timestamp)`
  - 共通: `rsi, atr, bb_width, volume_ratio, ma_distance, trend_efficiency`
  - RANGE系: `wick_ratio, mean_reversion_distance, reversal_candle_flag`
  - TREND系: `momentum_persistence, breakout_persistence, pullback_shallowness, higher_high_persistence`
  - 監査用: `feature_version, generated_at`

## 前提条件
- 特徴量は `timestamp` 時点までの情報のみで計算する（lookahead禁止）。
- 欠損を含む先頭区間は `warmup` として取引判定から除外する。
- 特徴量定義変更時は `feature_version` を更新する。

## 仕様
1. 計算ルール
- 窓長不足時はNaNを保持し、後段で除外。
- volume系はゼロ除算を防止し安全にクリップ。
- 同時刻に複数更新がある場合は最終確定candleのみ採用。

2. リーク防止
- `shift(-n)` 等の未来参照禁止。
- ラベル生成と特徴量計算の境界時刻を明示的に分離。
- 時系列shuffleを禁止し、常に昇順で処理。

3. 契約
- 主キー一意性は必須。
- 各特徴量のdtypeを固定（float/bool/int）。

## 失敗モードと対策
- 計算途中NaN過多: 指定閾値超過でジョブ失敗。
- 特徴量分布ドリフト: 監視メトリクスでアラート。
- バージョン不整合: 学習入力を拒否し再生成を要求。

## テスト観点
- 各特徴量の数式整合ユニットテスト。
- 主キー重複テスト。
- warmup除外テスト。
- リーク検知（未来参照）テスト。

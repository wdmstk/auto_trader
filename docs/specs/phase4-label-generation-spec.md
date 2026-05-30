# Phase 4 Spec: Label Generation

- Version: 1.0
- Date: 2026-05-30
- Related ADR: 0003

## 目的
TP/SL先着の2値ラベルを生成し、リークを防いだ学習データ基盤を提供する。

## 入力（I/O契約）
- 正規化OHLCVテーブル（Parquet）
  - 必須カラム: `symbol, timeframe, timestamp, close, high, low`
- ラベル設定
  - `tp_pct`（例: `0.04`）
  - `sl_pct`（例: `0.02`）
  - `max_horizon_bars`（探索最大バー数）

## 出力（I/O契約）
- ラベルテーブル（Parquet）
  - 主キー: `(symbol, timeframe, timestamp)`
  - カラム:
    - `label`（`1=TP first`, `0=SL first`, 未確定は `null`）
    - `hit_bars`
    - `tp_pct`, `sl_pct`, `max_horizon_bars`
    - `label_reason`
    - `label_version`, `generated_at`

## 前提条件
- 時系列は `timestamp` 昇順で処理する（no shuffle）。
- ラベルは未来バー探索で作るが、学習特徴量と同一timestampでのみ結合する。
- 同一バーで TP/SL 両方ヒット時は安全側で `SL first` とする。

## 仕様
1. ラベル生成
- エントリー価格は当該行 `close`。
- `tp = close * (1 + tp_pct)`、`sl = close * (1 - sl_pct)`。
- 次バー以降を `max_horizon_bars` まで探索し、先着イベントをラベル化する。

2. Timestamp整合
- symbol/timeframeごとに `timestamp` 単調増加を必須化。
- 重複timestampを禁止。

3. Leakage検証
- ラベル行は特徴量行と `(symbol,timeframe,timestamp)` で完全一致すること。
- 不一致行がある場合はジョブ失敗。

## 失敗モードと対策
- 時系列乱れ/重複: 事前バリデーションで失敗。
- 特徴量との不一致: leakage検証で失敗。
- horizon内未ヒット過多: ラベル偏りとして監視対象化。

## テスト観点
- `TP/SL` 先着の2値ラベルが正しく生成される。
- duplicate / 非単調timestampを検知できる。
- 特徴量とのtimestamp不一致を検知できる。

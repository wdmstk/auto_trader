# Phase 1 Spec: データ基盤

- Version: 1.0
- Date: 2026-05-30
- Related ADR: 0001, 0002

## 目的
Binance OHLCVを時系列整合性を保って取得・保存し、特徴量計算に安全に供給する。

## 入力（I/O契約）
- `symbol`（例: `BTCUSDT`, `ETHUSDT`）
- `timeframe`（例: `1m`, `5m`, `1h`）
- `from_ts`, `to_ts`（UTC）
- `mode`（`historical` or `incremental`）

## 出力（I/O契約）
- 正規化OHLCVテーブル（Parquet）
  - 主キー: `(symbol, timeframe, timestamp)`
  - カラム: `timestamp, open, high, low, close, volume, source, ingested_at`
  - `timestamp` は UTC, candle close time ベース
- データ品質レポート
  - `missing_count`, `duplicate_count`, `gap_ranges`, `last_synced_ts`

## 前提条件
- 時刻基準は全処理でUTC固定。
- rawデータと正規化データを分離する。
- 増分更新は `last_synced_ts` 以降のみ取得する。

## 仕様
1. 取得フロー
- historical: 指定期間をチャンク分割して順次取得。
- incremental: 最終同期時刻+1本目から取得しupsert。
- API失敗時は指数バックオフ再試行。

2. 検証フロー
- 欠損検知: timeframe間隔で連続性チェック。
- 重複検知: 主キー重複を拒否。
- 異常値検知: `high < low` や負値volumeを拒否。

3. 保存/キャッシュ
- 正規化データはParquetを正本とする。
- 特徴量再計算負荷低減のため、取得済み区間をキャッシュ管理。
- 再計算ポリシー: 元データ更新時のみ該当ウィンドウを部分再計算。

## 失敗モードと対策
- API rate limit: 再試行 + 待機 + 部分同期継続。
- ネットワーク断: 中断位置を記録し再開可能化。
- データ欠損継続: 取引停止アラートを発火（新規判定停止）。
- 重複混入: 書き込み前に主キー制約で弾く。

## テスト観点
- historical/incremental の整合性テスト。
- 欠損・重複検知ユニットテスト。
- UTC正規化テスト。
- 中断再開（リジューム）テスト。

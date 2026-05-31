# Phase 25 Spec: Gateway Rate Limit / Error Taxonomy / State Durability

- Version: 1.1
- Date: 2026-05-31
- Related ADR: 0001, 0002

## 目的
取引所レートリミット時の待機戦略を明確化し、gateway のエラー理由を構造化して通知・復旧の判断精度を高める。あわせて、実行中ポジション情報と未約定注文状態の永続化を強化し、破損・競合時の安全性を高める。

## 入力（I/O契約）
- 送信結果: `ok, order_id, reason`
- reason文字列（例: `timeout`, `network_error`, `rate_limit:retry_after=2`）

## 出力（I/O契約）
- 構造化エラー種別（Enum）
- 例外階層（ErrorCode整合）
- 注文イベント reason（標準化済みコード）
- リトライ時待機時間
- 永続化状態の整合性（atomic write / lock / recovery）

## 前提条件
- stale/high_vol/runtime gate は従来どおり最優先で reject する。
- rate limit は失敗扱いせず、待機後リトライ可能にする。

## 仕様
1. エラー分類
- `DUPLICATE_CLIENT_ORDER_ID`
- `STALE_SIGNAL`
- `GATING_BLOCKED`
- `RUNTIME_TRADING_DISABLED`
- `RUNTIME_EMERGENCY_STOP`
- `RUNTIME_STATE_INVALID`
- `RATE_LIMIT`
- `NETWORK_ERROR`
- `TIMEOUT`
- `SERVER_ERROR`
- `UNKNOWN_ERROR`

2. 待機戦略
- `RATE_LIMIT`: `retry_after` 指定があれば優先、なければ指数バックオフ。
- `NETWORK_ERROR/TIMEOUT/SERVER_ERROR`: 指数バックオフ + ジッター。
- 待機上限を `max_backoff_sec` で制限。

3. 失敗時出力
- 最終失敗時 reason は `retry_exhausted:<ERROR_CODE>` とする。

4. 例外階層
- `GatewayError` を基底とし、`RateLimitError` / `NetworkError` / `TimeoutError` / `ServerError` / `UnknownGatewayError` を定義する。
- 文字列reasonの分類結果は `ErrorCode` と例外の双方にマップし、後続の通知・自動復旧ロジックで再利用可能にする。

5. 状態永続化（State Durability）
- 対象: `positions.parquet`（ポジション状態）、`gateway_state.json`（未約定注文/seen client id）
- 書き込み方式:
  - 同一ディレクトリ内に一時ファイルへ書き込み
  - `fsync` 実行後に `os.replace` で原子的置換
  - 直前世代を `.bak` として保持
- 競合制御:
  - `.lock` ファイルを `O_CREAT|O_EXCL` で取得
  - 取得失敗時は短時間リトライし、タイムアウトで明示エラー
- 破損時復旧:
  - 読み込み失敗時は `.bak` から復旧を試行
  - `.bak` も破損時は安全側（空状態）へフォールバックし、ErrorCode整合の理由を返す

## 失敗モードと対策
- 429連発: backoff上限と試行回数で暴走防止。
- 未知reason: `UNKNOWN_ERROR` へフォールバックして追跡可能化。
- 書き込み競合: lock取得失敗で破壊的上書きを回避。
- 部分書き込み/破損: atomic replace + backup restore で復旧可能化。

## テスト観点
- `rate_limit` reason で待機し再試行すること。
- `retry_exhausted` 時に Enumコードが反映されること。
- 既存ゲート系 reject が維持されること。
- lock未取得時に失敗を検出できること。
- 破損ファイルから `.bak` 復旧できること。

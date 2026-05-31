# Phase 25 Spec: Gateway Rate Limit and Error Taxonomy

- Version: 1.0
- Date: 2026-05-31
- Related ADR: 0001, 0002

## 目的
取引所レートリミット時の待機戦略を明確化し、gateway のエラー理由を構造化して通知・復旧の判断精度を高める。

## 入力（I/O契約）
- 送信結果: `ok, order_id, reason`
- reason文字列（例: `timeout`, `network_error`, `rate_limit:retry_after=2`）

## 出力（I/O契約）
- 構造化エラー種別（Enum）
- 注文イベント reason（標準化済みコード）
- リトライ時待機時間

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

## 失敗モードと対策
- 429連発: backoff上限と試行回数で暴走防止。
- 未知reason: `UNKNOWN_ERROR` へフォールバックして追跡可能化。

## テスト観点
- `rate_limit` reason で待機し再試行すること。
- `retry_exhausted` 時に Enumコードが反映されること。
- 既存ゲート系 reject が維持されること。

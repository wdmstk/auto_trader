# Phase 10 Spec: Exchange Integration

- Version: 1.0
- Date: 2026-05-30
- Related ADR: 0001, 0002

## 目的
取引所接続を安全に実運用できるよう、注文実行・再接続・重複防止を統合する。

## 入力（I/O契約）
- 戦略シグナル（Phase 5/6）
- リスク判定結果
- API認証情報（環境変数）

## 出力（I/O契約）
- 注文イベントログ
  - `order_id, client_order_id, symbol, side, qty, status, reason`
- 実行結果テーブル
  - `requested_at, sent_at, ack_at, filled_at, latency_ms`

## 前提条件
- `isolated` のみ許可。
- 注文は冪等性キー（client order id）で一意管理。
- 失敗時は retry/reconnect を行うが、重複発注は禁止。

## 仕様
1. 接続
- REST + WebSocket のハイブリッド。
- WebSocket切断時は自動再接続。

2. 注文
- 発注前に最新リスク制約を再検証。
- `pass_filter=false` / `HIGH_VOL` は新規建て・追加建てを送信禁止。
- 既存ポジションを減らす `exit` / `emergency_close` は送信を許可する。

3. 障害対応
- timeout/reject/partial fill をハンドリング。
- 再送時は client order id を再利用して重複防止。

## 失敗モードと対策
- 切断ループ: backoff付き再接続。
- 重複注文: 冪等キー照合で拒否。
- stale signal: timestamp古いシグナルは破棄。

## テスト観点
- reconnect時に注文状態を復元できること。
- retryで重複注文が出ないこと。
- reject/partial fill の状態遷移が正しいこと。

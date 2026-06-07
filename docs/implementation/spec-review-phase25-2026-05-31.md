# Specレビュー結果（Phase 25）

- Date: 2026-05-31
- Scope: `phase25-gateway-rate-limit-and-error-taxonomy-spec.md`
- Reviewer: Codex

## 結論
Phase 25 は運用上の重要課題（429対応、reason標準化）を直接解消するため妥当。

## 固定事項
1. `retry_after` 優先待機
2. reason の Enum 標準化
3. 既存ゲートロジックの非破壊

## 残留リスク
- IP/Account weight を使った事前スロットリングは次段（State強化と併走）で実装が必要。

## 実装反映ステータス（2026-05-31）
- `src/auto_trader/exchange/errors.py` に ErrorCode Enum を追加済み。
- `src/auto_trader/exchange/gateway.py` に reason分類・retry_after優先待機・backoff/jitter を実装済み。
- 対応テスト: `tests/test_exchange_gateway.py`（rate limit再試行ケース含む）。

## 追加レビュー（State Durability 拡張）
1. `position` と `gateway` の動的状態は整合性要件が高く、通常書き込みでは破損リスクが残る。
2. 後続の通知/自動復旧連携を見据え、gatewayは reason文字列依存より `ErrorCode + 例外階層` が望ましい。
3. 既存原則（Regime-first / Risk-first / HIGH_VOL=NO TRADE）を維持したまま、永続化層のみを強化する。

## 追加決定事項（2026-05-31）
- atomic write（tmp + fsync + replace）を導入する。
- lock file（`O_CREAT|O_EXCL`）で同時更新競合を回避する。
- backup（`.bak`）からの復旧を既定経路にする。
- gateway分類は `ErrorCode` と `GatewayError` 系を同時に返せる形に拡張する。
- live 発注前に symbol precision を必ず正規化する。

## 実装反映ステータス追記（2026-05-31）
- `src/auto_trader/stateio.py` を追加し、atomic write / lock / json復旧基盤を導入。
- `src/auto_trader/position/store.py` へ lock + atomic parquet write + backup復旧を追加。
- `src/auto_trader/exchange/errors.py` へ `GatewayError` 階層を追加。
- `src/auto_trader/exchange/gateway.py` へ未約定注文/seen client id の永続化と復旧を追加。
- テスト追加:
  - `tests/test_position_store.py`（lock失敗・破損復旧）
  - `tests/test_exchange_gateway.py`（例外階層・gateway state復旧）

## Follow-up 方針（2026-05-31）
- 同一 durability 基盤を `runtime/control` と `notify` に横展開する。
- 既存の運用意味論（緊急停止・通知cooldown）は不変とし、I/O耐障害性のみ強化する。

## 追加レビュー（Precision Reject 対応, 2026-06-07）
1. `http_error:400:code=-1111` は再試行では解決しないため、gateway 手前での request 正規化が必要。
2. `qty` と `limit_price` を固定小数点で丸める実装は、symbol ごとの `stepSize/tickSize` に対して不十分。
3. 送信前に丸め、order event に正規化後の値を残すほうが運用調査に有利。
4. `minQty` 未満を取引所制約に合わせて増量するとリスク上限を超えるため、自動増量は禁止する。

## 実装反映ステータス追記（2026-06-07）
- `exchangeInfo` ベースの symbol precision キャッシュを transport に追加。
- worker は live 発注前に `qty/limit_price` を正規化し、order event に丸め後の値を保存。
- 丸め後の `qty` が `minQty` 未満の場合は、発注前に reject する。
- テスト追加:
  - `tests/test_exchange_rest_client.py`（stepSize/tickSize 正規化）

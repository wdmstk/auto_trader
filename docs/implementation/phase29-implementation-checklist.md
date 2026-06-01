# Phase 29 実装チェックリスト（Chaos Test Expansion）

## 実装前に固定する事項
- [x] stale検知遅延の `warn/fail` 閾値（秒）を固定
  - 初期値: `warn >= 30s`、`fail >= 120s`
- [x] partial fill 標準シナリオ（例: 10% fill + cancel）を固定
  - 初期値: `10% filled + 90% canceled` を基準ケースにする
- [x] emergency stop 発火条件（連続回数/秒数）を固定
  - 初期値: `stale critical` が `3サイクル連続` で `EMERGENCY_STOP`
- [x] 失敗時証跡の保存先を runbook と一致させる
  - 初期値: `data/validation/chaos/` 配下へ jsonl + summary を保存

## 実装項目
- [ ] partial fill 異常シナリオを追加
- [ ] silent websocket stale シナリオを追加
- [ ] stale検知レイテンシ計測を追加
- [ ] 緊急停止までのイベント証跡を追加
- [ ] chaosテスト実行スクリプトを追加
- [ ] テストを追加

## Done定義
- [ ] partial fill の状態整合テストが通る
- [ ] silent stale で検知->停止が再現する
- [ ] stale検知->停止のレイテンシが閾値内で評価できる
- [ ] 失敗時に原因特定可能な証跡を残せる
- [ ] spec-review を作成済み

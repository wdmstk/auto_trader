# 週次戦略再評価 Runbook（通知保留）

- Version: 1.0
- Date: 2026-06-01
- Scope: strategy quality revalidation (`range/trend`, 15m baseline)

## 目的
- 運用中に `PF/EXP/PnL/DD` が劣化していないかを週次で確認する。
- 通知運用（Phase 15/16）を投入せずに、手動確認ベースで継続改善する。

## 実行コマンド

```bash
./scripts/weekly_strategy_revalidation.sh
```

## 既定設定（Trial B baseline）
- timeframe: `15m`
- range symbols: `SOLUSDT,XRPUSDT,BNBUSDT`
- trend symbols: `ETHUSDT,XRPUSDT`
- range cooldown: `2`
- trend cooldown: `2`
- cost: `fee=0.0002, slippage=0.0002, spread=0.0001, delay=1`

## 暫定運用方針（2026-06-02）
- `trend`: `limit`
- `range`: `market`
- 暫定有効symbol:
  - `trend(limit)`: `ETHUSDT,XRPUSDT`
  - `range(market)`: `XRPUSDT`
- 一時除外:
  - `trend(limit)`: `BTCUSDT,BNBUSDT,SOLUSDT`
  - `range(market)`: `BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT`
- 判定根拠:
  - 採用条件は `PF > 1.2`, `EXPbps > 0`, `DD < 0.08`
  - `trend(limit)` では `ETHUSDT`, `XRPUSDT` が条件達成
  - `range(market)` では `XRPUSDT` のみ条件達成

## 成果物
- `data/validation/weekly_revalidation/timeframe_comparison_summary.json`
- `data/validation/weekly_revalidation/cost_grid_summary.jsonl`
- `data/validation/weekly_revalidation/cost_grid_result.json`
- `data/validation/weekly_revalidation/weekly_revalidation_report.json`

## 判定ルール
- `trend`: `PF >= 1.2`, `EXPbps > 0`, `PeriodPnL > 0`, `DD <= 0.08`
- `range`: `PF >= 1.2`, `EXPbps > 0`, `PeriodPnL > 0`, `DD <= 0.08`
- いずれか未達は `warn` 扱い（運用継続は可、symbol gating再調整を優先）。

## 運用メモ
- 通知は保留のため、本Runbookは手動実行＋手動レビュー前提。
- `status=warn` の場合:
  - `docs/implementation/timeframe-evaluation-2026-06-01.md` へ差分追記
  - `TREND_ENABLED_SYMBOLS` / `RANGE_ENABLED_SYMBOLS` を見直す
- 実注文経路の注文種別ポリシー（2026-06-02時点）:
  - 既定: `market`
  - `limit` 利用時: `IOC` 固定（未約定は cancel 固定）
  - 週次点検で `limit` を使う場合は、CLI で `--order-type limit --limit-price <price>` を必ず明示する
- monitor 追加観測値（limit運用監視）:
  - `gateway_pending_limit_orders`
  - `order_events_limit_count`
  - `order_events_limit_rejected_count`

## 約定モデルv2 キャリブレーション手順（新規）
1. `limit` 条件で週次再評価を実行し、指標を保存する。
   - 例:
     - `ORDER_MODES=limit ./scripts/timeframe_comparison.sh`
     - `ORDER_MODES=limit ./scripts/backtest_cost_grid.sh`
2. monitor 出力から `order_events_limit_count` と `order_events_limit_rejected_count` を確認する。
   - reject率目安:
     - `<= 0.30`: 許容
     - `0.30 - 0.50`: `warn`（queue/depth再調整）
     - `> 0.50`: `fail`（limit運用を縮小）
3. 調整ルール（週次で1項目のみ変更）:
   - 約定率が低すぎる: `limit_queue_ahead_units` を小さくする
   - 約定率が高すぎる: `limit_book_depth_units` を小さくする
   - 急変時の過大約定を抑制: `limit_volume_participation_rate` を小さくする
4. 変更履歴を `spec-review-phase27-2026-06-01.md` の追補に追記する。

## 週次実行の推奨コマンド（暫定）
```bash
TREND_ENABLED_SYMBOLS=ETHUSDT,XRPUSDT \
RANGE_ENABLED_SYMBOLS=XRPUSDT \
./scripts/weekly_strategy_revalidation.sh
```

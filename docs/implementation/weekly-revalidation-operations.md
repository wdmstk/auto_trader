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

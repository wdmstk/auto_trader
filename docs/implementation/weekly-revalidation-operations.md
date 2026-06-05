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

## 銘柄別の推奨モード（2026-06-03）
| 銘柄 | range | trend | 補足 |
|---|---|---|---|
| `BTCUSDT` | watchlist | watchlist | 15m では本線採用の根拠が弱い |
| `ETHUSDT` | 不採用 | `market` 基準 / `limit` 比較可 | market でも十分に良く、limit も検証価値あり |
| `SOLUSDT` | watchlist | watchlist | 15m では復帰しきれない |
| `XRPUSDT` | `market` 固定 | `market` 基準 / `limit` 比較可 | range は market が安定、trend は limit も強い |
| `BNBUSDT` | watchlist | watchlist | 現時点では本線採用の根拠が弱い |
| `ADAUSDT` | 不採用 | `market` 基準 / `limit` 比較可 | trend の新候補として有望 |

- 運用ルール:
  - `range` は `XRPUSDT` を `market` 固定で扱う
  - `trend` は `ETHUSDT / XRPUSDT / ADAUSDT` を中心に `market` を基準とし、`limit` は比較用途で使う
- `BTCUSDT / SOLUSDT / BNBUSDT` は即除外ではなく watchlist のまま残す

## 2026-06-05 follow-up（runtime_control_validation_suite の結果反映）
- 実測では `range` の週次集計は `XRPUSDT` のみが明確に強く、他銘柄はシグナルなしまたは採用根拠不足だった。
- `range(limit)` の `XRPUSDT` は `EXPbps < 0` で悪化しており、`limit` は現時点では診断用途に限定する。
- 週次の本線は次のように切り分ける。
  - `range`: `XRPUSDT` を `market` 固定
  - `trend`: `ETHUSDT / XRPUSDT / ADAUSDT` を中心に継続
  - `BTCUSDT / SOLUSDT / BNBUSDT / ADAUSDT` の `range` は watchlist 扱い
- `range` を Go/No-Go 判定に使う場合は、5銘柄平均ではなく `XRPUSDT market` の単独評価を優先する。
- 推奨再確認コマンド:
  - `RANGE_ENABLED_SYMBOLS=XRPUSDT ./scripts/weekly_strategy_revalidation.sh`
  - `SYMBOLS=XRPUSDT TIMEFRAMES=15m STRATEGIES=range ./scripts/timeframe_comparison.sh`

## 成果物
- `data/validation/weekly_revalidation/timeframe_comparison_summary.json`
- `data/validation/weekly_revalidation/timeframe_comparison_limit_summary.json`
- `data/validation/weekly_revalidation/cost_grid_summary.jsonl`
- `data/validation/weekly_revalidation/cost_grid_result.json`
- `data/validation/weekly_revalidation/weekly_revalidation_report.json`（`market` / `limit` 両方の要約を含む）
- `data/validation/weekly_revalidation/symbol_gating_recommendation.json`
- `data/validation/weekly_revalidation/symbol_gating.env`
- `data/validation/weekly_revalidation/limit_defaults.json`
- `data/validation/weekly_revalidation/limit_defaults.env`

## 判定ルール
- `trend`: `PF >= 1.2`, `EXPbps > 0`, `PeriodPnL > 0`, `DD <= 0.08`
- `range`: `PF >= 1.2`, `EXPbps > 0`, `PeriodPnL > 0`, `DD <= 0.08`
- いずれか未達は `warn` 扱い（運用継続は可、symbol gating再調整を優先）。

## 運用メモ
- 通知は保留のため、本Runbookは手動実行＋手動レビュー前提。
- 実行頻度の全体像は `docs/implementation/runtime-control-operations.md` の「実行頻度の目安」を参照する。
- `status=warn` の場合:
  - `docs/implementation/timeframe-evaluation-2026-06-01.md` へ差分追記
  - `TREND_ENABLED_SYMBOLS` / `RANGE_ENABLED_SYMBOLS` を見直す
- 実注文経路の注文種別ポリシー（2026-06-02時点）:
  - 既定: `market`
  - `limit` 利用時: `IOC` 固定（未約定は cancel 固定）
  - 週次点検で `limit` を使う場合は、CLI で `--order-type limit --limit-price <price>` を必ず明示する
- ML フィルタを使う場合:
  - `data/ml/artifacts/latest/metadata.json` が存在すれば `ML_ARTIFACT_PATH=data/ml/artifacts/latest` を自動採用する
  - 生成済み `signals` に `ml_score` / `ml_pass_filter` / `ml_model_version` が付与される
- monitor 追加観測値（limit運用監視）:
  - `gateway_pending_limit_orders`
  - `order_events_limit_count`
  - `order_events_limit_rejected_count`
  - `LimitFillRate`
  - `LimitTakerLikeRate`

## 約定モデルv2 キャリブレーション手順（新規）
1. `limit` 条件で週次再評価を実行し、指標を保存する。
   - 例:
     - `ORDER_MODES=limit ./scripts/timeframe_comparison.sh`
     - `ORDER_MODES=market,limit ./scripts/backtest_cost_grid.sh`
2. monitor 出力から `order_events_limit_count` と `order_events_limit_rejected_count` を確認する。
   - reject率目安:
     - `<= 0.30`: 許容
     - `0.30 - 0.50`: `warn`（queue/depth再調整）
     - `> 0.50`: `fail`（limit運用を縮小）
3. 調整ルール（週次で1項目のみ変更）:
   - 約定率が低すぎる: `limit_queue_ahead_units` を小さくする
   - 約定率が高すぎる: `limit_book_depth_units` を小さくする
   - 急変時の過大約定を抑制: `limit_volume_participation_rate` を小さくする
   - 週次標準 sweep では `limit_queue_ahead_units=0.02`、`limit_book_depth_units=0.0`、`limit_volume_participation_rate=0.0` を固定し、広い探索は診断時のみ行う
4. 変更履歴を `spec-review-phase27-2026-06-01.md` の追補に追記する。

## 週次実行の推奨コマンド（暫定）
```bash
TREND_ENABLED_SYMBOLS=ETHUSDT,XRPUSDT,ADAUSDT \
RANGE_ENABLED_SYMBOLS=XRPUSDT \
./scripts/weekly_strategy_revalidation.sh
```

`weekly_strategy_revalidation.sh` は `timeframe_comparison` を `market` と `limit` の両方で回し、cost-grid では `ORDER_MODES=market,limit` を既定にして `market` 基準と `limit` の maker 最適化を同時に比較します。
必要に応じて `ALLOWED_HOURS=18-23,0-1` を付けると JST セッションゲートを有効化できます。
15m 以外の候補探索は `./scripts/timeframe_candidate_scan.sh` で `15m,30m,1h` をまとめて評価します。
この候補探索は `ADAUSDT` / `DOGEUSDT` を含む拡張ユニバースを対象にできます（欠損時は 1m データを自動取得）。
2026-06-03 の候補探索では `ADAUSDT` が `core` に入り、`DOGEUSDT` は `watchlist` のままでした。
weekly の本線では `ADAUSDT` を `trend` の初期ユニバースに含め、`DOGEUSDT` は候補探索のまま保留します。

## 運用の位置づけ
- `weekly_strategy_revalidation.sh` は **週次の本線** で、バックテスト系検証のまとめ役。
- `timeframe_comparison.sh` / `backtest_cost_grid.sh` / `parallel_walkforward.sh` / `chaos_test.sh` は **必要時実行** の検証ジョブ。
- ライブ常駐ではなく、結果レビューのタイミングで回す前提。

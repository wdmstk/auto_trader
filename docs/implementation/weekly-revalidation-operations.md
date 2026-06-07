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
- range symbols: `SOLUSDT,XRPUSDT`
- trend symbols: `ETHUSDT,XRPUSDT`
- range cooldown: `2`
- trend cooldown: `2`
- cost: `fee=0.0002, slippage=0.0002, spread=0.0001, delay=1`

## 暫定運用方針（2026-06-02）
- `trend`: `limit`
- `range`: `market`
- 暫定有効symbol:
  - `trend(limit)`: `ETHUSDT,XRPUSDT`
  - `range(market)`: `SOLUSDT,XRPUSDT`
- 一時除外:
  - `trend(limit)`: `BTCUSDT,BNBUSDT,SOLUSDT`
  - `range(market)`: `BTCUSDT,ETHUSDT,BNBUSDT`
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
- 実測では `range` の週次集計は `XRPUSDT` が安定して強く、`SOLUSDT` も `wick_ratio_min=0.2` への緩和で本線採用に昇格できた。
- `range(limit)` は依然として `EXPbps < 0` で悪化するため、現時点では診断用途に限定する。
- 週次の本線は次のように切り分ける。
  - `range`: `SOLUSDT,XRPUSDT` を `market` 固定
  - `trend`: `ETHUSDT / XRPUSDT / ADAUSDT` を中心に継続
  - `BTCUSDT / BNBUSDT / ADAUSDT` の `range` は watchlist 扱い
- `range` を Go/No-Go 判定に使う場合は、5銘柄平均ではなく `SOLUSDT/XRPUSDT market` の選択銘柄評価を優先する。
- `SOLUSDT` は `wick_ratio_min=0.2` / `require_reversal_candle=false` の緩和条件で本線採用に昇格した。
- 推奨再確認コマンド:
  - `RANGE_ENABLED_SYMBOLS=SOLUSDT,XRPUSDT ./scripts/weekly_strategy_revalidation.sh`
  - `SYMBOLS=XRPUSDT TIMEFRAMES=15m STRATEGIES=range ./scripts/timeframe_comparison.sh`

## 成果物
- `data/validation/weekly_revalidation/timeframe_comparison_summary.json`
- `data/validation/weekly_revalidation/timeframe_comparison_limit_summary.json`
- `data/validation/weekly_revalidation/candidate_report.json`
- `data/validation/weekly_revalidation/result_list.md`
- `data/validation/weekly_revalidation/range_probe_result_list.md`
- `data/validation/weekly_revalidation/cost_grid_summary.jsonl`
- `data/validation/weekly_revalidation/cost_grid_result.json`
- `data/validation/weekly_revalidation/weekly_revalidation_report.json`（`market` / `limit` 両方の要約を含む）
- `data/validation/weekly_revalidation/symbol_gating_recommendation.json`
- `data/validation/weekly_revalidation/symbol_gating.env`
- `data/validation/weekly_revalidation/limit_defaults.json`
- `data/validation/weekly_revalidation/limit_defaults.env`

## レポート解釈
- `candidate_report.json` は route 正本であり、`route = symbol / strategy / timeframe` 単位の `rows` を保持する。
- 件数は `route_counts` と `symbol_counts` を分けて読む。
- `candidate_report.json` は `core / probe / watchlist` に加えて、`limit` 実績の要約（`filled / partial / expired / canceled / taker-like`）を含む。
- `weekly_revalidation_report.json` は `market` を本線判定、`limit` を診断判定として扱い、`decision` 系の理由情報を残す。
- `weekly_revalidation_report.json` の `selection.trade_routes` は全 `core` route を保持する。symbol dedupe はしない。
- GUI の `Overview` / `Trading` では、`core` 候補と `watchlist` 候補を分けて読み、`limit` 実績は補助情報として扱う。

## 判定ルール
- `trend`: `PF >= 1.2`, `EXPbps > 0`, `PeriodPnL > 0`, `DD <= 0.08`
- `range`: `PF >= 1.2`, `EXPbps > 0`, `PeriodPnL > 0`, `DD <= 0.08`
- `weekly_revalidation_report.json` の `status` は `market` 側を本線判定に使い、`limit` は診断用途として別保存する。
- `range` は `symbol_gating_recommendation.json` の `RANGE_ENABLED_SYMBOLS` に含まれる銘柄のみで採用判定する。
- いずれか未達は `warn` 扱い（運用継続は可、symbol gating再調整を優先）。

## 運用メモ
- 通知は保留のため、本Runbookは手動実行＋手動レビュー前提。
- 実行頻度の全体像は `docs/implementation/runtime-control-operations.md` の「実行頻度の目安」を参照する。
- 単発 backtest の TAT が 5 分未満なら日次で回し、5 分以上または複数 symbol / timeframe / parameter を振る検証は週次本線に寄せる。
- `python -m auto_trader.backtest ...` は軽量な単発確認向け、`./scripts/backtest_cost_grid.sh` はコスト感度や複数条件の比較向けとして使い分ける。
- 結果一覧の生成:
  - `./scripts/weekly_revalidation_results_list.sh`
- probe 一覧の生成:
  - `./scripts/weekly_revalidation_probe_results_list.sh`
- `status=warn` の場合:
  - `docs/implementation/timeframe-evaluation-2026-06-01.md` へ差分追記
  - `TREND_ENABLED_SYMBOLS` / `RANGE_ENABLED_SYMBOLS` を見直す
- `decision.reason` は `market_reason` / `limit_reason` / `drift_reason` を優先して読む。
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
RANGE_ENABLED_SYMBOLS=SOLUSDT,XRPUSDT \
./scripts/weekly_strategy_revalidation.sh
```

## 新規銘柄の探索ジョブ
- 週次本線とは分離して、新規 `USDT` 建て銘柄を探索するジョブを使う。
- 既存銘柄を除外したうえで、24h 流動性上位の新規候補を 10-20 銘柄ほど評価する。
- 既定の流動性下限は `MIN_QUOTE_VOLUME=30000000`。
- 探索コマンド:
  - `./scripts/symbol_candidate_exploration.sh`
- 結果一覧の生成:
  - `./scripts/symbol_candidate_results_list.sh`
- 週次シェルへの反映:
  - `./scripts/apply_weekly_core_candidates.sh`
- 生成物:
  - `data/validation/symbol_candidate_exploration/symbol_exploration_manifest.json`
  - `data/validation/symbol_candidate_exploration/timeframe_scan/candidate_report.json`
  - `data/validation/symbol_candidate_exploration/timeframe_scan/timeframe_comparison_summary.json`
  - `data/validation/symbol_candidate_exploration/result_list.md`
  - `data/validation/symbol_candidate_exploration/weekly_core_feedback.json`
  - `data/validation/symbol_candidate_exploration/weekly_core_feedback.env`
  - `data/validation/symbol_candidate_exploration/weekly_core_feedback.md`
- 採用ルール:
  - `candidate_report.json` の `core / probe / watchlist` で評価する
  - 週次本線への昇格は別レビューで判断し、`weekly_strategy_revalidation.sh` には自動反映しない
  - 既存の `BTCUSDT / ETHUSDT / SOLUSDT / XRPUSDT / BNBUSDT / ADAUSDT` は現状維持とする
- 週次へ反映する場合は `weekly_core_feedback.json` を route 正本として確認し、その後 `weekly_core_feedback.env` を `source` して `./scripts/weekly_strategy_revalidation.sh` を実行する
  - 定期実行では `./scripts/weekly_strategy_revalidation_with_core.sh` を使う

## 週次定期実行の設定例
`weekly_strategy_revalidation.sh` は **週次本線ジョブ** として定期実行する想定です。
出力先は `data/validation/timeframe_candidates` と `data/validation/weekly_revalidation` です。

### systemd user timer の例
テンプレート:
- `ops/systemd/auto-trader-weekly-revalidation.service.example`
- `ops/systemd/auto-trader-weekly-revalidation.timer.example`

`~/.config/systemd/user/auto-trader-weekly-revalidation.service`
```ini
[Unit]
Description=Auto Trader Weekly Revalidation

[Service]
Type=oneshot
WorkingDirectory=/home/komug/projects/auto_trader
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/komug/projects/auto_trader/scripts/weekly_strategy_revalidation_with_core.sh
StandardOutput=journal
StandardError=journal
```

`~/.config/systemd/user/auto-trader-weekly-revalidation.timer`
```ini
[Unit]
Description=Auto Trader Weekly Revalidation Timer

[Timer]
OnCalendar=Sun *-*-* 03:00:00
RandomizedDelaySec=2h
Unit=auto-trader-weekly-revalidation.service

[Install]
WantedBy=timers.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now auto-trader-weekly-revalidation.timer
systemctl --user status auto-trader-weekly-revalidation.timer
journalctl --user -u auto-trader-weekly-revalidation.service -f
```

### cron の例
```cron
0 3 * * 0 cd /home/komug/projects/auto_trader && ./scripts/weekly_strategy_revalidation_with_core.sh >> data/validation/weekly_revalidation/weekly_revalidation.cron.log 2>&1
```

`weekly_strategy_revalidation.sh` は `timeframe_comparison` を `market` と `limit` の両方で回し、cost-grid では `ORDER_MODES=market,limit` を既定にして `market` 基準と `limit` の maker 最適化を同時に比較します。
必要に応じて `ALLOWED_HOURS=18-23,0-1` を付けると JST セッションゲートを有効化できます。
15m 以外の候補探索は `./scripts/timeframe_candidate_scan.sh` で `15m,30m,1h` をまとめて評価します。
この候補探索は `ADAUSDT` / `DOGEUSDT` を含む拡張ユニバースを対象にできます（欠損時は 1m データを自動取得）。
2026-06-03 の候補探索では `ADAUSDT` が `core` に入り、`DOGEUSDT` は `watchlist` のままでした。
weekly の本線では `ADAUSDT` を `trend` の初期ユニバースに含め、`DOGEUSDT` は候補探索のまま保留します。
`BNBUSDT` は 15m の `range` ではまだ本線化しづらい一方、30m では `range` の採用余地が見えるため、次の拡張候補として 30m 側の probe を維持します。
`candidate_report.json` には `timeframe_reports` を追加し、`BNBUSDT` のような銘柄は 15m と 30m を分けて `core / probe / watchlist` を確認できます。
`weekly_strategy_revalidation.sh` は `RANGE_PROBE_SYMBOLS=BNBUSDT` のように設定すると、`range_probe_candidates` として 30m probe の別レポートも保存します。
`weekly_strategy_revalidation_with_core.sh` は週次定期実行向けのラッパーで、`result_list.md` と `range_probe_result_list.md` を本線の後に補助生成します。

## 運用の位置づけ
- `weekly_strategy_revalidation.sh` は **週次の本線** で、バックテスト系検証のまとめ役。
- `timeframe_comparison.sh` / `parallel_walkforward.sh` / `chaos_test.sh` は **必要時実行** の検証ジョブ。
- `backtest_symbol_rotation.sh` は **日次の live route 確認** で、`selection.trade_routes` を起点に自動売買対象だけを backtest する。
- `backtest_cost_grid.sh` は、単発 backtest の TAT が大きい場合や、複数条件を比較したい場合に **週次本線へ寄せる** 検証ジョブ。
- ライブ常駐ではなく、結果レビューのタイミングで回す前提。

## worker への自動反映
- `auto-trader-worker` は `data/validation/weekly_revalidation/weekly_revalidation_report.json` を定期的に読み直し、`selection.trade_routes` を live の `trade_routes` として反映できる。
- 反映対象は **symbol / regime / timeframe** の route 単位で、`trend` と `range` は別々の route として更新される。
- 同一 symbol に対して `trend` と `range` の両 route が `core` の場合、worker は両方を同時に保持する。
- `selection.trade_routes` が無い古いレポートは、`selection.trend_enabled_symbols` / `selection.range_enabled_symbols` を 15m の legacy route として扱う。
- 週次レポートが壊れている・未生成・読めない場合は、**前回の有効な symbol set を維持** する。
- `range_probe_candidates` はあくまで補助情報で、worker の自動売買対象には含めない。

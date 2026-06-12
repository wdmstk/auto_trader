# 週次戦略再評価 Runbook（通知保留）

- Version: 1.0
- Date: 2026-06-01
- Scope: strategy quality revalidation (`range/trend`, 15m baseline)

## 目的
- 運用中に `PF/EXP/PnL/DD` が劣化していないかを週次で確認する。
- 通知運用（Phase 15/16）を投入せずに、手動確認ベースで継続改善する。

## 実行コマンド

```bash
./scripts/ohlcv_coverage_check.sh
./scripts/weekly_strategy_revalidation.sh
```

正式運用で `autotune -> manifest -> weekly revalidation` を 1 本で回す場合は、
`./scripts/weekly_autotune_pipeline.sh` を使う。詳細は
`docs/implementation/route-selection-pipeline.md` を参照する。

この正式運用では、最終的な runtime 正本は
`data/validation/weekly_autotune/weekly_revalidation/weekly_revalidation_report.json`
になる。`manifest/route_selection_manifest.json` は週次前の tuned seed manifest として残す。
worker に渡す current env は `data/validation/weekly_autotune/route_selection_runtime.env`。

manifest route 再評価の並列既定:

- `WEEKLY_SCAN_PARALLEL=4`
- `WEEKLY_ROUTE_PARALLEL=4`
- `WEEKLY_ROUTE_DATA_PARALLEL=1`

`WEEKLY_SCAN_PARALLEL` は週次本体の `market/limit/range probe` 比較に使う。
`WEEKLY_ROUTE_PARALLEL` は manifest route 再評価の外側並列に使う。
まず外側を 4 並列にし、各 route 内の `timeframe_comparison.sh` は 1 のままにする。

manifest route 再評価では、`route_selection_manifest.json` に入っている route ごとの
`params` / `selected_stage` / `config_label` を保持したまま weekly rerun へ渡す。
つまり weekly の manifest-aware rerun は、同じ route key をデフォルト設定で回し直すのではなく、
autotune で選ばれた tuned route をそのまま週次条件で再監査する前提である。

統計 gate mode:

- `STATISTICAL_GATE_MODE=soft`
  - 検証フェーズ向け
  - `statistical_status=fail` でも route は `selection.trade_routes` に残し、診断ラベルとして扱う
- `STATISTICAL_GATE_MODE=hard`
  - 本番候補審査向け
  - 統計 fail route は `selection.trade_routes` から除外する

現状の既定は `soft`。

前提確認:
- `data/parquet/*_1m.parquet` の `Span Days` と `Gaps > Warn` を確認する
- coverage が不足している場合は `./scripts/multi_symbol_data_pipeline.sh` で OHLCV を再取得してから週次本線を回す
- 再取得 TAT を比較したい場合は `./scripts/multi_symbol_data_pipeline_benchmark.sh` を使う

補足:
- 既定では `RUN_COST_GRID=0` のため、重い `backtest_cost_grid.sh` は実行しない
- cost-grid を回したい場合のみ `RUN_COST_GRID=1 ./scripts/weekly_strategy_revalidation.sh` を使う
- `core` 拡大の設定調整は `./scripts/core_expansion_tuning.sh` を使う
- route 別の自動 tuning は `./scripts/core_route_autotune.sh` を使う

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

## 2026-06-09 follow-up（OHLCV修復と本線軽量化）
- `data/parquet/*_1m.parquet` の gap は downloader の pageing 不備が原因だった。
  - 1m データで Binance の `limit=1000` を超える区間を 1 request で取り切れず、約 55 時間単位の欠損を再生産していた。
  - `download_historical_ohlcv()` を pageing 対応に修正し、`ohlcv_coverage_check.sh` で gap=0 を確認した。
- 週次本線の TAT は `weekly_strategy_revalidation.sh` 全体で約 16 時間 46 分かかり、運用上は長すぎた。
  - 支配的だったのは `backtest_cost_grid.sh` で、本線の route 選定・統計ゲート確認とは役割が異なる。
- 運用判断:
  - 当面は `market` 優先で環境を整える。
  - `limit` は診断用途に留め、実運用の既定にはしない。
  - `backtest_cost_grid.sh` は毎週必須ではなく、必要時のみ `RUN_COST_GRID=1` で明示実行する。
- 実務上の使い分け:
  - 本線: `./scripts/weekly_strategy_revalidation.sh`
  - 重い診断込み: `RUN_COST_GRID=1 ./scripts/weekly_strategy_revalidation.sh`
  - cost-grid は `market / limit` の execution 前提比較と `limit_defaults` の見直し用であり、route 選定の必須条件ではない。

## 2026-06-09 latest result summary（OHLCV修復後の統計結果）
- OHLCV 側は改善完了。
  - `data/validation/ohlcv_coverage_1m.md` では全 9 symbol が `Status=ok`、`Gaps > Warn=0`、`Max Gap Min=1.00` になった。
  - つまり、今回の fail 要因は OHLCV の期間不足や大きな欠損ではない。
- 週次本線の結論は `warn` のまま。
  - `weekly_revalidation_report.json` の `status=warn`
  - `decision.candidate_reason.status=pass` だが `decision.statistical_reason.status=fail`
  - `selection.trade_routes=[]` で、live 昇格 route は 0 件
- 候補の母集団は残っている。
  - `core routes=1, probe routes=1, watchlist routes=10`
  - ただし core 候補 1 件も statistical qualification を通過できず、fail-closed で除外された
- 実際に統計ゲートで落ちた route:
  - `trend:SOLUSDT:15m`
  - `closed_trades=40`
  - `oos_days=47.42`
  - 件数・OOS 期間は最低条件を満たしたが、性能指標が悪化して fail
  - fail 理由: `pf`, `expectancy_bps`, `period_pnl`, `pf_ci_lower`, `expectancy_bps_ci_lower`, `mc_loss_probability`
  - 実値: `pf=0.504`, `expectancy_bps=-13.98`, `period_pnl=-5.05`, `mc_loss_probability=0.9134`
- 解釈:
  - OHLCV 修復で「データ不備のせいで判定不能」という段階は抜けた
  - その上でなお統計的に通らないため、現状の課題はデータ品質ではなく strategy quality 側にある
  - この週次結果では `trend_enabled_symbols=[]`、`range_enabled_symbols=[]` となり、本線採用 symbol はなし

## 2026-06-09 core expansion follow-up（全銘柄・gatingなし比較）
- `*_ENABLED_SYMBOLS` を空にした全銘柄比較では `core=3`, `probe=5`, `watchlist=28` だった。
- `blocked / signal_0 / trade_0` を見分けるため、`timeframe_comparison_result_list.md` に次を追加した。
  - `Gating`
  - `Signal_0`
  - `Trade_0`
  - `Signal Count`
  - `Trade Count`
- 読み方:
  - `blocked`: `signal_reason_codes` が全行 `*_BLOCK_SYMBOL_DISABLED`
  - `signal_0=yes`: signal は 1 件も成立していない
  - `trade_0=yes`: walkforward の closed trade が 0 件
  - `core` 拡大の母集団は `gating=pass` かつ `trade_0=no` の route のみに限定する
- 直近の短期昇格候補:
  - `range:SOLUSDT:30m`
  - `trend:ETHUSDT:15m`
  - `trend:ADAUSDT:1h`
  - `trend:ETHUSDT:1h`
  - `range:XRPUSDT:30m`
- 中期ロジック改善候補:
  - `range:BNBUSDT:30m`
  - `range:BTCUSDT:1h`
  - `range:ADAUSDT:15m`
  - `trend:XRPUSDT:1h`
  - `trend:ETHUSDT:15m`

## 成果物
- `data/validation/weekly_revalidation/timeframe_comparison_summary.json`
- `data/validation/weekly_revalidation/timeframe_comparison_limit_summary.json`
- `data/validation/weekly_revalidation/candidate_report.json`
- `data/validation/weekly_revalidation/result_list.md`
- `data/validation/weekly_revalidation/range_probe_result_list.md`
- `data/validation/weekly_revalidation/cost_grid_summary.jsonl`
- `data/validation/weekly_revalidation/cost_grid_result.json`
- `data/validation/weekly_revalidation/weekly_revalidation_report.json`（`market` / `limit` 両方の要約を含む）
- `data/validation/weekly_autotune/weekly_revalidation/manifest_vs_weekly_diff.json`
- `data/validation/weekly_autotune/weekly_revalidation/manifest_vs_weekly_diff.md`

## 統計 fail の切り分け
`qualification_report.json` だけでは route ごとの fold 偏りや worst trade が見えにくい。
次で route 別の fail 診断を出せる。

```bash
./scripts/statistical_fail_diagnostics_report.sh
```

既定出力:

- `data/validation/weekly_autotune/weekly_revalidation/statistical_fail_diagnostics.json`
- `data/validation/weekly_autotune/weekly_revalidation/statistical_fail_diagnostics.md`

`OUTPUT_JSON` / `OUTPUT_MD` を明示しない場合は、`ANALYSIS_DIR` から見た
同一 run の `weekly_revalidation` 配下へ自動で出す。

見方:

- `category=sample_thin`
  - edge 自体はあるが OOS trade 数が足りず、`pf_ci_lower` / `expectancy_bps_ci_lower` / `mc_loss_probability` が落ちる
  - まずは trade 数を増やす方向で見る
- `category=oos_quality`
  - 最終 OOS fold で `pf` / `expectancy_bps` / `period_pnl` 自体が崩れている
  - 単なるデータ蓄積ではなく route 調整か降格が必要
- `data/validation/weekly_revalidation/symbol_gating_recommendation.json`
- `data/validation/weekly_revalidation/symbol_gating.env`
- `data/validation/weekly_revalidation/limit_defaults.json`
- `data/validation/weekly_revalidation/limit_defaults.env`
- `data/validation/core_expansion/core_expansion_tuning_summary.json`
- `data/validation/core_expansion/core_expansion_tuning_summary.md`
- `data/validation/core_expansion/fold_breakdown.md`
- `data/validation/core_expansion/trend_next_step_summary.json`
- `data/validation/core_expansion/trend_next_step_summary.md`
- `data/validation/core_expansion/trend_provisional_core_summary.json`
- `data/validation/core_expansion/trend_provisional_core_summary.md`
- `data/validation/core_expansion/trend_entry_threshold_summary.json`
- `data/validation/core_expansion/trend_entry_threshold_summary.md`
- `data/validation/core_expansion/trend_entry_diagnostics.json`
- `data/validation/core_expansion/trend_entry_diagnostics.md`
- `data/validation/core_expansion/loss_fold_review.json`
- `data/validation/core_expansion/loss_fold_review.md`
- `data/validation/core_expansion/loss_fold_trade_detail.json`
- `data/validation/core_expansion/loss_fold_trade_detail.md`
- `data/validation/core_expansion/loss_hold_threshold.json`
- `data/validation/core_expansion/loss_hold_threshold.md`
- `data/validation/core_expansion/hold_exit_summary.json`
- `data/validation/core_expansion/hold_exit_summary.md`
- `data/validation/core_expansion/regime_threshold_summary.json`
- `data/validation/core_expansion/regime_threshold_summary.md`

## レポート解釈
- `candidate_report.json` は route 正本であり、`route = symbol / strategy / timeframe` 単位の `rows` を保持する。
- 件数は `route_counts` と `symbol_counts` を分けて読む。
- `candidate_report.json` は `core / probe / watchlist` に加えて、`limit` 実績の要約（`filled / partial / expired / canceled / taker-like`）を含む。
- `weekly_revalidation_report.json` は `market` を本線判定、`limit` を診断判定として扱い、`decision` 系の理由情報を残す。
- `weekly_autotune_pipeline.sh` / `weekly_strategy_revalidation_with_core.sh` で manifest seed を使って週次を回した場合は、
  実行後に `manifest_vs_weekly_diff.json/md` も同じ `weekly_revalidation` 配下へ自動生成する。
- 同時に `weekly_revalidation_report.json` にも `manifest_weekly_diff` 要約が埋め込まれる。
  - `metric_match_count`: manifest 採用時と weekly rerun で指標が一致した route 数
  - `oos_window_drift_count`: 指標は一致するが、統計 qualification 側の fold OOS 窓だけが広がった route 数
  - GUI `Overview` の `Manifest vs Weekly drift` はこの要約を表示する
- `RUN_COST_GRID=0` の場合、`limit_defaults.json/env` は現在の `FEE_RATE / SLIPPAGE_RATE / SPREAD_RATE / DELAY_BARS` をそのまま記録する。
- `weekly_revalidation_report.json` の `selection.trade_routes` は全 `core` route を保持する。symbol dedupe はしない。
- GUI の `Overview` / `Trading` では、`core` 候補と `watchlist` 候補を分けて読み、`limit` 実績は補助情報として扱う。
- `timeframe_comparison_result_list.md` では、`blocked` route を性能評価対象に含めない。
- `Signal_0=yes` は「未成立」、`Trade_0=yes` は「backtest不成立」として扱い、閾値比較とは分ける。

## 判定ルール
- `trend`: `PF >= 1.2`, `EXPbps > 0`, `PeriodPnL > 0`, `DD <= 0.08`
- `range`: `PF >= 1.2`, `EXPbps > 0`, `PeriodPnL > 0`, `DD <= 0.08`
- live昇格には `data/validation/statistical_qualification/qualification_report.json` の
  route・strategy両方の `status=pass` を必須とする。
- 統計条件は route 30件、strategy 100件、最終OOS 30日かつ20%以上、
  bootstrap 95% CI、Monte Carlo DD/損失確率で判定する。
- frozen OOS manifest不一致または統計レポート未取得時はfail-closedとし、
  対象routeをwatchlistへ降格して `selection.trade_routes` から除外する。
- `weekly_revalidation_report.json` の `status` は `market` 側を本線判定に使い、`limit` は診断用途として別保存する。
- `range` は `symbol_gating_recommendation.json` の `RANGE_ENABLED_SYMBOLS` に含まれる銘柄のみで採用判定する。
- いずれか未達は `warn` 扱い（運用継続は可、symbol gating再調整を優先）。

## 運用メモ
- 通知は保留のため、本Runbookは手動実行＋手動レビュー前提。
- 実行頻度の全体像は `docs/implementation/runtime-control-operations.md` の「実行頻度の目安」を参照する。
- 単発 backtest の TAT が 5 分未満なら日次で回し、5 分以上または複数 symbol / timeframe / parameter を振る検証は必要時の診断ジョブとして扱う。
- `python -m auto_trader.backtest ...` は軽量な単発確認向け、`./scripts/backtest_cost_grid.sh` はコスト感度や複数条件の比較向けとして使い分ける。
- 結果一覧の生成:
  - `./scripts/weekly_revalidation_results_list.sh`
- probe 一覧の生成:
  - `./scripts/weekly_revalidation_probe_results_list.sh`
- `status=warn` の場合:
  - `docs/implementation/timeframe-evaluation-2026-06-01.md` へ差分追記
  - `TREND_ENABLED_SYMBOLS` / `RANGE_ENABLED_SYMBOLS` を見直す
- `decision.reason` は `market_reason` / `limit_reason` / `drift_reason` を優先して読む。
- `core` 拡大の設定調整ジョブ:
  - `./scripts/core_expansion_tuning.sh`
- route 別の自動探索ジョブ:
  - `./scripts/core_route_autotune.sh`
  - 詳細は `docs/implementation/core-route-autotune.md` を参照
- `max_hold_bars` の妥当性判断:
  - まず `PF >= 1.2`, `EXPbps > 0`, `PeriodPnL > 0`, `DD <= 0.08` の `core` 条件に近づくかで判定する
  - 単独指標では決めず、`PF / EXPbps / PeriodPnL / DD` を同時に比較する
  - `trade_count` が極端に減る設定は避け、`trade_count < 10` なら改善しても暫定扱いに留める
  - 改善が 1 fold だけに偏っていないかを `fold_breakdown.md` で確認する
  - `loss_hold_threshold.md` は「長時間保有の負け trade を早く切れたらどこまで改善余地があるか」の上限診断として使う
  - 実際の採用値は「その戦略の失敗パターンを、収益を壊さずに早く切れる最小の bar 数」を優先する
  - `trend` では「伸びる勝ちを待つ時間」ではなく「失敗した trend をどこで諦めるか」を見る
  - `range` では「反発待ちの典型時間を超えてコスト負けする前に切れているか」を見る
- fold 別 breakdown の単独生成:
  - `ROUTES=trend:ETHUSDT:15m,range:SOLUSDT:30m ./scripts/walkforward_fold_breakdown_report.sh`
  - 隔離 run_data を読む場合:
    - `DATA_ROOT=data/validation/core_expansion_run3/baseline_all_symbols/run_data ROUTES=trend:ETHUSDT:15m ./scripts/walkforward_fold_breakdown_report.sh`
- 全 route の負け fold 横断レビュー:
  - `CANDIDATE_REPORT_PATH=data/validation/core_expansion_run6/baseline_all_symbols/candidate_report.json DATA_ROOT=data/validation/core_expansion_run6/baseline_all_symbols/run_data ./scripts/loss_fold_review_report.sh`
- 負け fold の trade 明細レビュー（既定は悪い順の上位 route）:
  - `LOSS_FOLD_REVIEW_JSON=data/validation/core_expansion_run6/loss_fold_review.json CANDIDATE_REPORT_PATH=data/validation/core_expansion_run6/baseline_all_symbols/candidate_report.json DATA_ROOT=data/validation/core_expansion_run6/baseline_all_symbols/run_data ./scripts/loss_fold_trade_detail_report.sh`
- 長時間保有の負け trade 影響レビュー:
  - `LOSS_FOLD_REVIEW_JSON=data/validation/core_expansion_run6/loss_fold_review.json CANDIDATE_REPORT_PATH=data/validation/core_expansion_run6/baseline_all_symbols/candidate_report.json ANALYSIS_DIR=data/validation/core_expansion_run6/baseline_all_symbols/run_data/analysis ./scripts/loss_hold_threshold_report.sh`
- `core_expansion_tuning.sh` の既定方針:
  - `gating` なし
  - `market` 前提固定
  - 次段の `trend` 対応では `trend_efficiency_exit_threshold` も sweep する
  - entry 条件の詰まり確認後は `trend_breakout_persistence_min / trend_momentum_persistence_min / trend_pullback_shallowness_min / trend_higher_high_persistence_min` を sweep する
  - hold 起因の悪化が強い route では `range_max_hold_bars / trend_max_hold_bars` を sweep する
  - hold で改善余地が薄く、`regime_entry_diagnostics.md` で `trend_mask_not_adopted` が多い route では `regime_threshold_matrix` を回す
  - 初手の regime 調整対象は `trend:BTCUSDT:1h` とし、`REGIME_TREND_ADX_THRESHOLD / REGIME_TREND_BREAKOUT_PERSISTENCE_MIN_BARS / MIN_REGIME_HOLD_BARS / HIGH_VOL_COOLDOWN_BARS` を sweep する
  - 2026-06-11 時点では `trend:BTCUSDT:1h` は regime 緩和後も `watchlist` のままとし、既定の tuning 母集団からは外す
  - baseline の trend route については `trend_entry_diagnostics.md` で `gate_open / eligible / all4_ok / entry` と failure signature を確認する
  - regime 側を診る場合は `regime_entry_diagnostics.md` で `trend_regime_rows / regime_trend_mask_rows / trend_mask_not_adopted_rows / top_regime_reasons` を確認する
  - `trade_count < 10` の `core` は暫定 core として別扱い
  - 既定で `ON`:
    - `RUN_BASELINE=1`
    - `RUN_TREND_NEXT_STEP_MATRIX=1`
    - `RUN_TREND_ENTRY_THRESHOLD_MATRIX=1`
    - `RUN_HOLD_EXIT_MATRIX=1`
    - `RUN_TREND_ENTRY_DIAGNOSTICS=1`
    - `RUN_FOLD_BREAKDOWN=1`
    - `RUN_LOSS_FOLD_REVIEW=1`
    - `RUN_LOSS_FOLD_TRADE_DETAIL=1`
    - `RUN_LOSS_HOLD_THRESHOLD=1`
  - 既定で `OFF`:
    - `RUN_RANGE_MATRIX=0`
    - `RUN_TREND_MATRIX=0`
    - `RUN_TREND_PROVISIONAL_CORE_MATRIX=0`
    - `RUN_BUILD_TREND_PROVISIONAL_CORE_REPORT=0`
    - `RUN_REGIME_THRESHOLD_MATRIX=0`
    - `RUN_BUILD_REGIME_THRESHOLD_REPORT=0`
  - 必要時だけ明示的に `RUN_*=1` で有効化する
  - TAT 短縮のため hold 系だけ回す場合:
    - `TUNING_PROFILE=hold_only ./scripts/core_expansion_tuning.sh`
    - この profile では `baseline + hold_exit_matrix + loss_hold_threshold + hold_exit_summary` のみを既定で実行し、trend/range の他 matrix と重い診断を止める
  - hold 改善だけを細粒度で詰める場合:
    - `TUNING_PROFILE=hold_fine ./scripts/core_expansion_tuning.sh`
    - 対象 route は `range:ETHUSDT:15m`, `trend:ETHUSDT:1h`, `range:XRPUSDT:1h`
    - 既定 sweep は `range=20/24/28 bars`, `trend=3/4/5/6 bars`
  - hold 系の case 並列数を個別に絞る場合:
    - `HOLD_CASE_PARALLEL=1 TUNING_PROFILE=hold_fine ./scripts/core_expansion_tuning.sh`
  - regime 側の閾値改善を個別に回す場合:
    - `OUT_DIR=data/validation/core_expansion_regime_run1 TUNING_PROFILE=regime_only ./scripts/core_expansion_tuning.sh`
    - `REGIME_CASE_PARALLEL=1` などで case 並列数を個別に調整できる
    - この profile では `baseline_all_symbols + regime_threshold_matrix + regime_threshold_summary` を既定で実行し、それ以外は停止する
    - `OUT_DIR=data/validation/core_expansion_regime_run1 RUN_BASELINE=1 RUN_TREND_NEXT_STEP_MATRIX=0 RUN_TREND_ENTRY_THRESHOLD_MATRIX=0 RUN_HOLD_EXIT_MATRIX=0 RUN_REGIME_THRESHOLD_MATRIX=1 RUN_TREND_ENTRY_DIAGNOSTICS=0 RUN_FOLD_BREAKDOWN=0 RUN_LOSS_FOLD_REVIEW=0 RUN_LOSS_FOLD_TRADE_DETAIL=0 RUN_LOSS_HOLD_THRESHOLD=0 RUN_BUILD_AGGREGATE_REPORT=0 RUN_BUILD_TREND_NEXT_STEP_REPORT=0 RUN_BUILD_TREND_ENTRY_THRESHOLD_REPORT=0 RUN_BUILD_HOLD_EXIT_REPORT=0 RUN_BUILD_REGIME_THRESHOLD_REPORT=1 ./scripts/core_expansion_tuning.sh`
- trend entry 診断の単独生成:
  - `DATA_ROOT=data/validation/core_expansion_run5/baseline_all_symbols/run_data ROUTES=trend:ETHUSDT:15m,trend:ETHUSDT:1h ./scripts/trend_entry_diagnostics_report.sh`
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

cost-grid も含めて診断したい場合:
```bash
RUN_COST_GRID=1 \
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
- 旧運用では `weekly_core_feedback.env` を `source` して `./scripts/weekly_strategy_revalidation.sh` を実行していたが、
  正式運用では `./scripts/weekly_autotune_pipeline.sh` を使う

## 週次定期実行の設定例
`weekly_autotune_pipeline.sh` は **週次本線ジョブ** として定期実行する想定です。
出力先は `data/validation/weekly_autotune` です。

### systemd user timer の例
テンプレート:
- [auto-trader-weekly-revalidation.service.example](/home/komug/projects/auto_trader/ops/systemd/auto-trader-weekly-revalidation.service.example:1)
- [auto-trader-weekly-revalidation.timer.example](/home/komug/projects/auto_trader/ops/systemd/auto-trader-weekly-revalidation.timer.example:1)

```bash
cp ops/systemd/auto-trader-weekly-revalidation.service.example ~/.config/systemd/user/auto-trader-weekly-revalidation.service
cp ops/systemd/auto-trader-weekly-revalidation.timer.example ~/.config/systemd/user/auto-trader-weekly-revalidation.timer
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now auto-trader-weekly-revalidation.timer
systemctl --user status auto-trader-weekly-revalidation.timer
journalctl --user -u auto-trader-weekly-revalidation.service -f
```

### cron の例
```cron
0 3 * * 0 cd /home/komug/projects/auto_trader && RUN_ROOT=data/validation/weekly_autotune ./scripts/weekly_autotune_pipeline.sh >> data/validation/weekly_autotune/weekly_autotune.cron.log 2>&1
```

`weekly_strategy_revalidation.sh` は `timeframe_comparison` を `market` と `limit` の両方で回します。
`backtest_cost_grid.sh` は既定では本線から外し、`RUN_COST_GRID=1` のときだけ `ORDER_MODES=market,limit` 既定で `market` 基準と `limit` の maker 最適化を比較します。
必要に応じて `ALLOWED_HOURS=18-23,0-1` を付けると JST セッションゲートを有効化できます。
15m 以外の候補探索は `./scripts/timeframe_candidate_scan.sh` で `15m,30m,1h` をまとめて評価します。
この候補探索は `ADAUSDT` / `DOGEUSDT` を含む拡張ユニバースを対象にできます（欠損時は 1m データを自動取得）。
2026-06-03 の候補探索では `ADAUSDT` が `core` に入り、`DOGEUSDT` は `watchlist` のままでした。
weekly の本線では `ADAUSDT` を `trend` の初期ユニバースに含め、`DOGEUSDT` は候補探索のまま保留します。
`BNBUSDT` は 15m の `range` ではまだ本線化しづらい一方、30m では `range` の採用余地が見えるため、次の拡張候補として 30m 側の probe を維持します。
`candidate_report.json` には `timeframe_reports` を追加し、`BNBUSDT` のような銘柄は 15m と 30m を分けて `core / probe / watchlist` を確認できます。
`weekly_strategy_revalidation.sh` は `RANGE_PROBE_SYMBOLS=BNBUSDT` のように設定すると、`range_probe_candidates` として 30m probe の別レポートも保存します。
旧 `weekly_strategy_revalidation_with_core.sh` は後方互換のラッパーとして残すが、
週次定期実行の既定は `weekly_autotune_pipeline.sh` とする。

## 運用の位置づけ
- `weekly_strategy_revalidation.sh` は **週次の本線** で、route 選定と統計ゲート確認のまとめ役。
- `timeframe_comparison.sh` / `parallel_walkforward.sh` / `chaos_test.sh` は **必要時実行** の検証ジョブ。
- `backtest_symbol_rotation.sh` は **日次の live route 確認** で、`selection.trade_routes` を起点に自動売買対象だけを backtest する。
- `backtest_cost_grid.sh` は、単発 backtest の TAT が大きい場合や、複数条件を比較したい場合の **診断ジョブ**。
- ライブ常駐ではなく、結果レビューのタイミングで回す前提。

## worker への自動反映
- `auto-trader-worker` は `data/validation/weekly_revalidation/weekly_revalidation_report.json` を定期的に読み直し、`selection.trade_routes` を live の `trade_routes` として反映できる。
- 反映対象は **symbol / regime / timeframe** の route 単位で、`trend` と `range` は別々の route として更新される。
- 同一 symbol に対して `trend` と `range` の両 route が `core` の場合、worker は両方を同時に保持する。
- `selection.trade_routes` が無い古いレポートは、`selection.trend_enabled_symbols` / `selection.range_enabled_symbols` を 15m の legacy route として扱う。
- 週次レポートが壊れている・未生成・読めない場合は、**前回の有効な symbol set を維持** する。
- `range_probe_candidates` はあくまで補助情報で、worker の自動売買対象には含めない。

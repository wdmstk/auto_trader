# Timeframe Evaluation Record (1m vs 5m vs 15m)

- Date: 2026-06-01
- Scope: BTCUSDT/ETHUSDT/SOLUSDT/XRPUSDT/BNBUSDT, strategy=range+trend
- Data source: existing `data/parquet/*_1m.parquet` resampled to 5m/15m
- Evidence:
  - `scripts/timeframe_comparison.sh`
  - `data/validation/timeframe_eval/timeframe_comparison_summary.json`

## Execution

```bash
./scripts/timeframe_comparison.sh
```

## Summary

- Aggregate (`trend`, initial run):
  - `1m`: `pf=0.005`, `max_dd=0.0798`, `monthly_pnl=-795.63`
  - `5m`: `pf=0.000`, `max_dd=0.0142`, `monthly_pnl=-141.37`
  - `15m`: `pf=0.000`, `max_dd=0.0041`, `monthly_pnl=-39.71`
- Aggregate (`range`):
  - `1m/5m/15m` すべてで `pf=0.000`, `max_dd=0.0000`, `monthly_pnl=0.00`

## Re-run (BTCUSDT only, longer window)

- Date: 2026-06-01
- Scope: `BTCUSDT`（約1か月: 2026-01-01 〜 2026-01-31）
- Command:
  - `SYMBOLS=BTCUSDT ./scripts/timeframe_comparison.sh`
- Trend result:
  - `1m`: `pf=0.000`, `max_dd=0.3930`, `monthly_pnl=-3919.76`
  - `5m`: `pf=0.000`, `max_dd=0.0696`, `monthly_pnl=-696.39`
  - `15m`: `pf=0.000`, `max_dd=0.0202`, `monthly_pnl=-197.47`
- Interpretation:
  - BTCの1か月比較でも、`15m` が最もDDと損失を抑制。
  - 安全性優先の観点で `15m(regime) + 5m(signal) + 1m(execution)` は妥当。

## Re-run (5 symbols, 3-month window)

- Date: 2026-06-01
- Scope: `BTCUSDT/ETHUSDT/SOLUSDT/XRPUSDT/BNBUSDT`（2026-01-01 〜 2026-04-01）
- Commands:
  - `FROM_TS=2026-01-01T00:00:00+00:00 TO_TS=2026-04-01T00:00:00+00:00 TIMEFRAME=1m ./scripts/multi_symbol_data_pipeline.sh`
  - `./scripts/timeframe_comparison.sh`
- Trend aggregate:
  - `1m`: `pf=0.1164`, `max_dd=0.1842`, `monthly_pnl=-1810.56`, `win_rate=0.0642`
  - `5m`: `pf=0.1182`, `max_dd=0.0606`, `monthly_pnl=-601.03`, `win_rate=0.0895`
  - `15m`: `pf=1.4723`, `max_dd=0.0247`, `monthly_pnl=-40.11`, `win_rate=0.1250`
- Trend best timeframe by symbol:
  - `BTCUSDT: 15m`
  - `ETHUSDT: 15m`
  - `SOLUSDT: 5m`
  - `XRPUSDT: 15m`
  - `BNBUSDT: 15m`

## Re-run (Range threshold tuning)

- Date: 2026-06-01
- Rationale:
  - `reversal_candle_flag` が実データでほぼ `0` のため、range entryが閉じていた。
- Tuning:
  - `RANGE_REQUIRE_REVERSAL_CANDLE=false`
  - `RANGE_WICK_RATIO_MIN=0.3`
- Command:
  - `RANGE_REQUIRE_REVERSAL_CANDLE=false RANGE_WICK_RATIO_MIN=0.3 ./scripts/timeframe_comparison.sh`
- Result (aggregate):
  - Range `1m`: `pf=0.1138`, `max_dd=0.1722`, `monthly_pnl=-1706.00`, `win_rate=0.0955`
  - Range `5m`: `pf=0.6690`, `max_dd=0.0692`, `monthly_pnl=-515.08`, `win_rate=0.2456`
  - Range `15m`: `pf=4.1819`, `max_dd=0.0542`, `monthly_pnl=-84.74`, `win_rate=0.4543`
- Entry count (5 symbols total):
  - Range `1m`: `2386`
  - Range `5m`: `629`
  - Range `15m`: `178`

## Interpretation

- 3か月・5銘柄の再評価でも、`15m` は `1m`/`5m` より DD を抑制しつつ PF が最良。
- `15m` が 5銘柄中4銘柄の最良時間足となり、symbol差を考慮しても優位性が高い。
- Rangeは閾値調整で成立不足を解消でき、時間足評価の妥当性が向上した。

## Decision (Current)

- Adopt:
  - Regime: `15m`
  - Signal generation: `5m`
  - Execution timing: `1m`
- Status: `Conditional Go`
  - 時間足方針は `15m(regime) + 5m(signal) + 1m(execution)` を採用候補として確定。
  - Range閾値は運用で再学習/最適化を継続（本評価では `require_reversal=false`, `wick>=0.3` を採用）。

## PnL / Expectancy Follow-up (2026-06-01)

- Implementation update:
  - Backtest metrics に `ExpectancyBps`, `PeriodPnL`, `GrossPnLEst`, `TotalCostEst`, `FeeCost`, `ImpactCostEst`, `ClosedTrades` を追加。
  - Walkforward summary に上記指標を保存。
- 3か月・5銘柄 aggregate（range調整後）:
  - Trend `15m`: `PF=1.4723`, `DD=0.0247`, `PeriodPnL=-40.11`, `EXP=-19.0780`, `EXPbps=-13.8280`, `Cost=112.99`, `GrossPnLEst=72.87`
  - Range `15m`: `PF=4.1819`, `DD=0.0542`, `PeriodPnL=-84.74`, `EXP=-62.5922`, `EXPbps=21.6537`, `Cost=186.73`, `GrossPnLEst=101.99`
- Interpretation:
  - `GrossPnLEst` がプラスでも `TotalCostEst` で `PeriodPnL` がマイナス化しており、主因はコスト負け。
  - 直近優先課題は「エッジ抽出」より「取引密度・コスト最適化（約定回数抑制 / コスト仮定再校正）」。

## Cost Grid Trial (2026-06-01)

- Added:
  - `scripts/backtest_cost_grid.sh`
  - `auto_trader.analysis` が `fee/slippage/spread/delay` を受け取れるよう拡張。
- Trial scope:
  - `TIMEFRAMES=15m`, `STRATEGIES=range,trend`, `delay=1`
  - feeのみ比較（`0.0002` vs `0.0004`）
- Command:
  - `FEE_RATES=0.0002,0.0004 SLIPPAGE_RATES=0.0002 SPREAD_RATES=0.0001 DELAY_BARS_LIST=1 TIMEFRAMES=15m ./scripts/backtest_cost_grid.sh`
- Result:
  - Best: `fee=0.0002`, `slippage=0.0002`, `spread=0.0001`, `delay=1`
  - Trend 15m: `EXPbps=-0.53`, `PeriodPnL=+25.79`, `PF=2.42`, `DD=0.0215`
  - Range 15m: `EXPbps=+35.69`, `PeriodPnL=+24.19`, `PF=14.62`, `DD=0.0502`
- Evidence:
  - `data/validation/cost_grid/cost_grid_summary.jsonl`
  - `data/validation/cost_grid/cost_grid_result.json`

## Cost Grid Expansion (2026-06-01)

- Scope:
  - `fee: 0.0002/0.0003/0.0004`
  - `slippage: 0.0002/0.0005`
  - `spread: 0.0001/0.0003`
  - `delay: 0/1/2`
  - total `36` cases (`15m`, `range+trend`)
- Command:
  - `FEE_RATES=0.0002,0.0003,0.0004 SLIPPAGE_RATES=0.0002,0.0005 SPREAD_RATES=0.0001,0.0003 DELAY_BARS_LIST=0,1,2 TIMEFRAMES=15m ./scripts/backtest_cost_grid.sh`
- Best case (same as small trial):
  - `fee=0.0002`, `slippage=0.0002`, `spread=0.0001`, `delay=1`
  - Trend 15m: `EXPbps=-0.53`, `PeriodPnL=+25.79`, `PF=2.42`, `DD=0.0215`
  - Range 15m: `EXPbps=+35.69`, `PeriodPnL=+24.19`, `PF=14.62`, `DD=0.0502`
- Robustness note:
  - `delay=1` は `delay=0/2` より総合スコアが安定。
  - `fee` と `spread` が悪化すると `PeriodPnL` は急速に悪化（cost sensitivity 高）。

## Signal Gating Trial (2026-06-01)

- Goal:
  - 低品質シグナルの除外で `PF/EXP/PnL` を改善する。
- Added capabilities:
  - `min_entry_score`
  - `reentry_cooldown_bars`
  - `enabled_symbols`（銘柄別ON/OFF）
- Trial A:
  - Range: `enabled=SOLUSDT,XRPUSDT,BNBUSDT`, `cooldown=2`
  - Trend: `enabled=ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT`, `cooldown=2`
  - Aggregate (`15m`):
    - Trend: `PF=2.3122`, `EXPbps=-1.9130`, `DD=0.0008`, `PeriodPnL=+4.06`
    - Range: `PF=1.3221`, `EXPbps=+65.2576`, `DD=0.0006`, `PeriodPnL=+1.52`
- Trial B (trend銘柄をさらに選別):
  - Range: same as Trial A
  - Trend: `enabled=ETHUSDT,XRPUSDT`, `cooldown=2`
  - Aggregate (`15m`):
    - Trend: `PF=2.2094`, `EXPbps=+13.5530`, `DD=0.0007`, `PeriodPnL=+4.50`
    - Range: `PF=1.3221`, `EXPbps=+65.2576`, `DD=0.0006`, `PeriodPnL=+1.52`
- Interim recommendation:
  - `trend` は symbol gating を前提に運用（`ETHUSDT,XRPUSDT` を first set）
  - `range` は `SOLUSDT,XRPUSDT,BNBUSDT` を first set
  - 週次で同評価を再実行し、ON/OFF symbol を更新

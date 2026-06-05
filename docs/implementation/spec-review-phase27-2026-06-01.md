# Specレビュー結果（Phase 27）

- Date: 2026-06-01
- Scope: `docs/specs/phase27-limit-order-and-maker-cost-optimization-spec.md`
- Reviewer: Codex

## 結論
Phase 27 は実装完了し、market互換維持のまま limit/maker 評価導線を追加できている。
状態遷移（filled/partial/expired/canceled）と cost-grid の order_mode 比較が動作しており、仕様意図と整合する。

## 固定事項
1. market モードは互換維持し、limit モードを追加する。
2. `filled/partial/expired/canceled` の状態遷移を必須証跡化する。
3. 成果判定は `gross/net/cost` の一貫性で評価する。
4. 週次標準 sweep では `limit_queue_ahead_units=0.02`、`limit_book_depth_units=0.0`、`limit_volume_participation_rate=0.0` を固定し、広い探索は診断時のみ行う。

## 実装結果（2026-06-01）
- `BacktestConfig` に `order_mode` / `maker_fee_rate` / `taker_fee_rate` を追加。
- limit約定モデル v1 を実装（タッチ時 partial、1bar 滞留で filled、未成立は expired）。
- partial fill の残数量は v1 で `canceled` 固定を実装。
- `timeframe_comparison.sh` / `backtest_cost_grid.sh` に order_mode 導線を追加。
- `cost_grid_result.json` に `order_mode` 次元を反映。
- 検証:
  - `tests/test_backtest_simulator.py` / `tests/test_backtest_pipeline.py` pass
  - `ORDER_MODES=limit ./scripts/backtest_cost_grid.sh` で比較出力確認

## 追補（2026-06-02: 実注文経路の最小拡張）
- `src/auto_trader/exchange/models.py`
  - `OrderRequest` に `order_type`（`market|limit`、既定 `market`）と `limit_price` を追加。
- `src/auto_trader/exchange/cli.py`
  - `--order-type` / `--limit-price` を追加。
  - `limit` 指定時に `--limit-price` 未指定は reject（入力不正）とする。
- `src/auto_trader/exchange/rest_client.py`
  - `type=MARKET` 固定を廃止し、`order_type` を送信値に反映。
  - `LIMIT` 時は `timeInForce=IOC` を固定し、未約定時は cancel 固定ポリシーに一致させる。
- 追加検証:
  - `tests/test_exchange_rest_client.py`: LIMIT(IOC) パラメータ送信 / limit_price必須
  - `tests/test_exchange_cli.py`: CLI引数導線 / limit_price未指定reject
  - `tests/test_monitor_cli.py`: limit監視メトリクス集計（pending/event/rejected）

## 追補（2026-06-02: 約定モデルv2の近似導入）
- `src/auto_trader/backtest/simulator.py`
  - limit partial fill 計算に板厚/queue近似を追加:
    - `limit_book_depth_units`
    - `limit_queue_ahead_units`
    - `limit_volume_participation_rate`
  - 既定値は `0` とし、未指定時は従来の `limit_partial_fill_ratio` ロジックを維持。
- `src/auto_trader/backtest/cli.py` / `src/auto_trader/analysis/cli.py`
  - 上記3パラメータをCLIから指定可能に拡張。
- `src/auto_trader/analysis/walkforward.py`
  - walkforward設定から backtest へ新パラメータを伝播。
- 追加検証:
  - `tests/test_backtest_simulator.py`
    - queue先行量により partial fill が減ること
    - 既定値で旧挙動が維持されること

## 追補（2026-06-02: symbol gating 暫定方針）
- 比較条件:
  - `fee=0.0002`, `slippage=0.0002`, `spread=0.0001`, `delay=1`
  - `trend=limit`, `range=market`
  - 判定条件: `PF > 1.2`, `EXPbps > 0`, `DD < 0.08`
- 結果:
  - `trend(limit)` 達成: `ETHUSDT`, `XRPUSDT`
  - `range(market)` 達成: `XRPUSDT`
  - `BTCUSDT` は trend で `DD=0.0982` により未達
  - `BNBUSDT`, `SOLUSDT` は trend/range とも `PF/EXPbps` 未達
- 暫定運用:
  - `trend(limit)` は `ETHUSDT,XRPUSDT`
  - `range(market)` は `XRPUSDT`
  - 他symbolは週次再評価まで gating 維持

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

## 残留リスク
- 板厚・queue position は v2 で近似導入済みだが、固定パラメータのため実約定との乖離余地がある。
- maker前提崩壊（taker化率）の監視閾値は運用チューニングが必要。

## 次アクション
- gross/net/cost の一貫性チェックを自動テストで強化する。
- 約定モデルの改善は以下の順で進める（過学習回避のため段階投入）:
  1. v2固定パラメータを2-4週間運用し、実績差分を収集する。
     - 追跡指標: 想定約定率/実約定率、想定partial率/実partial率、limit reject率
  2. `queue_ahead` の時間減衰モデルを追加する（バー経過で先行数量が減る近似）。
  3. GTC近似（最大Nバー持ち越し）を追加し、IOC固定との差分を比較する。
  4. 銘柄別の板厚初期値を導入し、単一パラメータ運用を卒業する。

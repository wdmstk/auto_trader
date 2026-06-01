# add_policy 導入計画（段階適用）

- Date: 2026-06-01
- Source: `add_policy.md`
- Positioning: `base_policy.md` を置換せず、拡張要件として段階導入する

## 目的
- `base_policy.md` の安全原則（regime/risk/execution safety）を維持したまま、
  マルチ銘柄運用・並列処理・可観測性を拡張する。

## 前提
- 既存は単銘柄（`BTCUSDT_1m`）中心の導線が主。
- Futures testnet と runtime gate の検証は成立済み。
- 通知本番投入は Go-Live 後タスク。

## 導入方針
1. 安全性を壊さない順序で導入する（risk/guardrail先行）。
2. 先に「動く」より先に「止められる」を担保する。
3. 各段階で証跡（テスト・レポート・運用手順）を残す。

## Phase A: Multi-Symbol Data 基盤
- Scope:
  - 複数銘柄のOHLCV取得・保存（symbol別ファイル管理）
  - features/regime/signal を symbol 単位で生成可能にする
- Deliverables:
  - symbolループ実行CLI（またはジョブ）
  - symbol別出力ディレクトリ/命名規約
- Done:
  - `BTC/ETH/SOL/XRP/BNB` の最小5銘柄で同一パイプライン完走
  - 1銘柄失敗時に他銘柄処理が継続（failure isolation）
- Progress:
  - `scripts/multi_symbol_data_pipeline.sh` を追加済み（failure isolation + summary出力）。

## Phase B: Portfolio Risk Manager
- Scope:
  - 単銘柄ではなく portfolio basis の risk 判定
  - correlated exposure 制限（同方向集中の抑止）
- Deliverables:
  - portfolio risk evaluation（新規テーブル）
  - order gate への portfolio block reason 追加
- Done:
  - 高相関ロング集中時に新規建てが拒否されるテスト
  - DD/Exposure の portfolio閾値を超えたとき fail-safe 動作
- Progress:
  - `RiskConfig.max_correlated_exposure_pct` を追加済み。
  - `RISK_CORRELATED_EXPOSURE` 判定とテストを追加済み。
  - `scripts/enrich_risk_input_with_correlation.sh` で `correlated_exposure_pct` 補完導線を追加済み。
  - `scripts/risk_correlated_exposure_check.sh` で相関集中ブロックの証跡取得を追加済み。

## Phase C: Multi-Symbol GUI
- Scope:
  - symbol list / regime / pnl / dd / exposure を一覧表示
  - heatmap / ranking / correlation matrix の可視化
- Deliverables:
  - Streamlit 新パネル（既存画面の拡張）
  - キャッシュと遅延描画（lazy rendering）
- Done:
  - 5銘柄同時表示で描画崩れなし
  - 操作レスポンス遅延が実用範囲（運用者確認）
- Progress:
  - Streamlitに `Multi-Symbol Panel` を追加済み。
  - symbol list / regime / close / range-trend entry件数 / ranking を表示可能。
  - PnL/DD/Exposure 表示を追加済み。
  - 1分リターン相関行列（correlation matrix）を追加済み。
  - regime map / correlation matrix をヒートマップ表示可能に更新済み。
  - symbol別 walkforward 指標（PF/WinRate/DD/PnL）表示を追加済み。
  - walkforward成果物を symbol/timeframe 単位の命名へ拡張済み（GUIは新旧命名を両対応）。

## Phase D: Parallel Walkforward / Backtest
- Scope:
  - symbol別 walkforward/backtest の並列実行
  - fold × symbol の比較レポート
- Deliverables:
  - 並列ランナー（`concurrent.futures` を第一候補）
  - 実行時間比較ベンチ（単発 vs 並列）
- Done:
  - 同条件で TAT 改善を定量確認
  - 結果再現性（再実行差分が許容範囲）
- Progress:
  - `scripts/parallel_walkforward.sh` を追加済み（symbol×strategy 並列実行 + summary証跡）。
  - `scripts/parallel_walkforward_benchmark.sh` を追加済み（逐次/並列のTAT比較証跡）。
  - 実測（2026-06-01）:
    - sequential: `7 sec`
    - parallel: `3 sec`
    - speedup: `2.33x`
    - 証跡: `data/validation/parallel_walkforward_benchmark.json`

## Phase E: Async 実行基盤（段階投入）
- Scope:
  - websocket/リアルタイム処理の非同期化
  - queue backlog/latency監視
- Deliverables:
  - async runner（非ブロッキング設計）
  - 監視メトリクス（CPU/メモリ/遅延）
- Done:
  - リアルタイム処理でボトルネック可視化
  - 過負荷時の劣化挙動が運用ルール化されている
- Progress:
  - Streamlit `st.cache_data`（TTL付き）を導入済み。
  - Multi-Symbol Panel に heavy visualization トグルを追加し、lazy rendering を適用済み。
  - `python -m auto_trader.monitor` を追加済み（runtime/gateway/risk/order events からメトリクス集約）。
  - `gateway_pending_orders` / `order_latency_p95_ms` を json/jsonl で取得可能。
  - GUI に Runtime Metrics パネルを追加済み（monitor出力jsonlを読み取り表示）。
  - GUIに Health 判定（OK/WARNING/CRITICAL）を追加済み。
  - `scripts/runtime_metrics_health_check.sh` を追加済み（Go/No-Goしきい値を自動採点）。
  - `scripts/longrun_8h_check.sh` 終了時に health check 自動実行を連携済み。

## 技術選定ガイド（初期）
- 並列:
  - 第1段階: `concurrent.futures.ProcessPoolExecutor`
  - 第2段階: `joblib`（ML系）
  - 将来候補: `Ray` / `Dask`（規模拡大時）
- キャッシュ:
  - parquet優先 + feature cache
  - Streamlit: `st.cache_data` / `st.cache_resource`
- スケジューラ:
  - 初期は cron/systemd
  - 拡張時にジョブオーケストレータ検討

## リスクと対策
- リスク: 相関管理なしで見かけ上の分散
  - 対策: correlated exposure gate を B で最優先導入
- リスク: 並列化で再現性低下
  - 対策: seed固定・入出力スナップショット
- リスク: GUI多銘柄化で重い
  - 対策: lazy rendering + 表示件数上限 + キャッシュ

## 現時点の優先実行順
1. Phase A（multi-symbol data）
2. Phase B（portfolio risk）
3. Phase D（parallel walkforward）
4. Phase C（multi-symbol GUI）
5. Phase E（async）

## Go/No-Go 判定基準（add_policy 対応）
- Go:
  - 5銘柄でパイプライン安定
  - portfolio risk gate が機能
  - 並列WFでTAT改善と再現性を確認
- Conditional Go:
  - GUI拡張が未完でも運用安全要件を満たす
- No-Go:
  - 相関集中を抑制できない
  - failure isolation が機能しない

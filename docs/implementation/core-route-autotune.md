# Core Route Autotune

- Version: 1.0
- Date: 2026-06-11
- Scope: `core` 候補 route の自動探索と route 別 tuning 実行

## 目的

これまでの `core` 拡大は、次の手順を手動で繰り返していた。

1. baseline 全銘柄比較
2. `probe` / `watchlist` の中から候補 route を人手で抽出
3. `hold` の sweep
4. `trend` なら `exit` / `entry threshold` sweep
5. 必要時だけ `regime` sweep
6. 結果を比較して `core / provisional_core / watchlist` を判断

この手順は route 数が増えると TAT が伸びやすく、毎回の意思決定も重い。
`core_route_autotune.sh` はこの流れを route 単位で自動実行し、最終的な結論を `json/md` にまとめる。

既定モードは `expansion` で、`probe` と近傍 `watchlist` から新規 `core` 候補を探す。
`TARGET_SELECTION_MODE=core_refinement` を指定すると、baseline 時点で `core` の route だけを再チューニングして
既存 core の改善余地を探す。

## 実行コマンド

正式運用で `autotune -> manifest -> weekly revalidation` を 1 本で回す場合は、
`docs/implementation/route-selection-pipeline.md` の `./scripts/weekly_autotune_pipeline.sh` を使う。
このページのコマンドは、個別 stage を単独実行したいときの詳細手順として扱う。

```bash
OUT_DIR=data/validation/core_route_autotune_run1 \
ROUTE_PARALLEL=2 \
STAGE_CASE_PARALLEL=4 \
STAGE_DATA_PARALLEL=1 \
./scripts/core_route_autotune.sh
```

baseline core の refinement だけを回す場合:

```bash
OUT_DIR=data/validation/core_route_refinement_run1 \
TARGET_SELECTION_MODE=core_refinement \
TARGET_ROUTE_LIMIT=8 \
ROUTE_PARALLEL=2 \
STAGE_CASE_PARALLEL=4 \
STAGE_DATA_PARALLEL=1 \
./scripts/core_route_autotune.sh
```

## 自動化フロー

### 1. Baseline

- `core_expansion_tuning.sh` を baseline のみで 1 回実行する
- `candidate_report.json` から route 母集団を作る

### 2. Target Selection

- `TARGET_SELECTION_MODE=expansion`
  - `core` は除外する
  - `probe` は優先対象に入れる
  - `watchlist` は次のような「core に近い route」だけを対象に入れる
    - `DD <= 0.15`
    - かつ `PF >= 1.0` または `EXPbps > -10` または `PeriodPnL > 0`
- `TARGET_SELECTION_MODE=core_refinement`
  - baseline 時点で `candidate_status=core` の route だけを対象にする
  - `probe` / `watchlist` は対象外

### 3. Route-local Tuning

- `range`
  - `hold`
  - 未解決なら `range_matrix`
- `trend`
  - `hold`
  - 未解決なら `trend_next_step`
  - 未解決なら `trend_entry_threshold`
  - `regime_entry_diagnostics` で `trend_mask_not_adopted` 比率が高い場合のみ `regime_threshold`

各 route は独立した `OUT_DIR/routes/<route>/...` に保存されるため、route 間は並列実行できる。

`core_refinement` では、baseline がすでに `core_confirmed` でも `STOP_ON_CONFIRMED_CORE` による早期打ち切りをせず、
hold / trend-next / trend-entry / regime まで回した上で最良設定を選ぶ。
`AUTO_RUN_REGIME` の既定は `true` のままで、`regime_threshold` を実行しても最終採用は固定せず、
常に全フェーズ中の最良結果を selected とする。

## 出力

- `auto_tune_targets.json`
  - baseline 後に選ばれた route 一覧
- `auto_tune_summary.json`
  - route ごとの stage 実行結果と最終判定
- `auto_tune_summary.md`
  - 人が読むための要約
- `routes/<route>/...`
  - route 別の tuning 実行結果
  - stage ごとの構造は `routes/<route>/<stage>/cases/<config>/...`
  - `cases/` 直下の各 config はその stage の case 実行結果
- `autotune_core_feedback.json`
  - 採用候補 route と選択パラメータの manifest
  - `core_refinement` では baseline core を置き換える候補差分
- `autotune_core_feedback.env`
  - `SYMBOLS / TREND_ENABLED_SYMBOLS / RANGE_ENABLED_SYMBOLS` の簡易 env
- `autotune_core_feedback.md`
  - 採用候補 route の人向け一覧
- `autotune_route_manifest.json`
  - worker / GUI が読める `selection.trade_routes` 互換 manifest
  - `core_refinement` では refinement 対象 route の差分 manifest
- `autotune_route_manifest.md`
  - manifest の人向け一覧
- `autotune_full_route_manifest.json`
  - baseline 既存 core と autotune 追加 core を統合した full manifest
  - `core_refinement` では same route key の baseline core を selected route で上書きした runtime 正本
- `autotune_full_route_manifest.md`
  - full manifest の人向け一覧

## 最終判定

- `core_confirmed`
  - `candidate_status=core`
  - かつ `closed_trades_mean >= PROVISIONAL_CORE_MIN_TRADES`
- `core_provisional`
  - `candidate_status=core`
  - だが trade 数が不足
- `no_core_found`
  - 自動化済み stage の範囲では `core` に到達しなかった

## 並列化

- `ROUTE_PARALLEL`
  - route 単位の外側並列
  - 既定 `2`
- `STAGE_CASE_PARALLEL`
  - 各 stage の case 並列
  - 既定 `4`
- `STAGE_DATA_PARALLEL`
  - 各 case 内の `timeframe_comparison.sh` 並列
  - 既定 `1`
- `HOLD_CASE_PARALLEL`
  - hold stage だけ case 並列数を変えたい場合の上書き
- `REGIME_CASE_PARALLEL`
  - regime stage だけ case 並列数を変えたい場合の上書き

運用上は、まず `ROUTE_PARALLEL=2`, `STAGE_CASE_PARALLEL=4`, `STAGE_DATA_PARALLEL=1` を既定とする。
旧 `AUTOTUNE_PARALLEL` / `AUTOTUNE_CASE_PARALLEL` / `PARALLEL` / `CASE_PARALLEL` も後方互換で残すが、
新規運用では上の 3 つだけを使う。

## 主な環境変数

- `OUT_DIR`
  - 実行結果の保存先
- `TARGET_ROUTE_LIMIT`
  - 自動探索の最大 route 数
- `TARGET_SELECTION_MODE`
  - `expansion` または `core_refinement`
- `MAX_WATCHLIST_TARGETS`
  - watchlist から拾う最大 route 数
- `PROVISIONAL_CORE_MIN_TRADES`
  - provisional 判定の閾値。既定 `10`
- `STOP_ON_CONFIRMED_CORE`
  - confirmed core が出た route は次 stage を打ち切る。既定 `true`
- `AUTO_RUN_REGIME`
  - trend route の regime fallback を有効化する。既定 `true`
- `REGIME_BLOCK_RATIO`
  - `trend_mask_not_adopted / regime_trend_mask` がこの比率以上なら regime sweep を走らせる

## 採用候補設定の出力

autotune 完了後に、採用候補を `env/json/md` へ落とす。

```bash
SUMMARY_PATH=data/validation/core_route_autotune_run3/auto_tune_summary.json \
./scripts/apply_autotune_core_candidates.sh
```

この出力のうち、

- `autotune_core_feedback.env`
  - 現行 runtime がそのまま使える symbol enable 系の最小出力
- `autotune_core_feedback.json`
  - route ごとの選択 stage とパラメータ詳細
  - `selection_mode=core_refinement` の場合、ここに載る route は baseline core を置き換える候補差分
- `autotune_route_manifest.json`
  - `selection.trade_routes` 互換
  - `expected_regime`, `timeframe`, `candidate_status`, `statistical_status`, `params` を含む
  - autotune 増分だけを見たい時の manifest
- `autotune_full_route_manifest.json`
  - baseline core も含めた統合 manifest
  - `core_refinement` では same route key の baseline core を selected route で無条件に置き換える
  - weekly 前の runtime seed 候補はこちら

を使い分ける。

worker に autotune 統合 manifest を渡す場合は、`ROUTE_SELECTION_PATH` を使う。

```bash
ROUTE_SELECTION_PATH=data/validation/core_route_autotune_run3/autotune_full_route_manifest.json \
AUTO_SYNC_ROUTE_SELECTION=1 \
python -m auto_trader.worker --watch --interval-sec 2
```

`WEEKLY_REVALIDATION_REPORT_PATH` も後方互換で引き続き使えるが、autotune manifest を正本にする場合は
`ROUTE_SELECTION_PATH` を優先する。

## 制約

- これは `route` の候補探索と tuning 自動化であり、live 昇格そのものではない
- live 昇格には別途 `statistical_qualification` が必要
- `range` の自動探索は現時点では `hold + range_matrix` まで
- `trend` の自動探索は現時点では `hold + next_step + entry_threshold + optional regime` まで
- 大幅赤字や `DD` 超過 route は、自動化しても `watchlist` のまま終わることがある

## baseline run_data の扱い

- baseline の `run_data` は後続 stage の immutable source として再利用する
- 特に `1m parquet` / resampled OHLCV / features / regime は、baseline に存在する場合は後続 stage が再利用する
- 一方で `signals` と `analysis` は parameter 依存なので、case ごとに独立した出力を持つ
- そのため route-local tuning では `cases/<config>/run_data` が残るが、これは「baseline を無視している」のではなく、
  parameter 依存 artefact を衝突なく並列実行するための隔離領域である

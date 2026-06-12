# Route Selection Pipeline

- Version: 1.0
- Date: 2026-06-12
- Scope: `autotune -> manifest -> weekly revalidation` の正式運用導線

## 目的

`core_route_autotune` と `weekly_strategy_revalidation` は、どちらも route 選別に関係するため、
個別に手で回すと次の問題が起きやすい。

- 実行順がぶれやすい
- 出力ディレクトリが散らばりやすい
- どの manifest を runtime 正本にするか曖昧になりやすい
- `expansion` と `core_refinement` の結果を人手でマージする必要がある

正式運用では、これらを 1 本のコマンドで回せるようにし、成果物を 1 つの run root 配下へ集約する。

## 基本方針

- 人が叩く入口は 1 本にする
- ただし処理責務そのものは分離する
  - `autotune`: route 探索と設定調整
  - `weekly revalidation`: 週次の品質監査と統計確認
- `RUN_WEEKLY=1` の正式運用では、runtime/GUI が読む route 正本は
  `weekly_revalidation/weekly_revalidation_report.json` とする
- `manifest/route_selection_manifest.json` は weekly 前の tuned seed manifest として残す
- `weekly revalidation` は tuned manifest を seed に route ごとの再評価を行い、
  週次の最終 `selection.trade_routes` を再生成する

## 役割分担

### 1. `autotune`

役割:

- `probe/watchlist` から新規 core 候補を探す
- baseline core の改善余地を `core_refinement` で詰める
- route ごとの selected stage / selected params を決める
- runtime/GUI が読める `selection.trade_routes` manifest を出力する

出力:

- `autotune_summary.json/md`
- `autotune_core_feedback.json/env/md`
- `autotune_route_manifest.json/md`
- `autotune_full_route_manifest.json/md`

### 2. `weekly revalidation`

役割:

- 週次の本線 baseline 条件で route 群を再監査する
- `weekly_strategy_revalidation.sh` を単独実行し、`ROUTE_SELECTION_PATH` が与えられた場合は、
 その manifest の各 route を、manifest に保存された個別 params / selected stage を保ったまま再評価する
- candidate / statistical / drift の fail-closed 判定を残す
- 今週の監査結果を `weekly_revalidation_report.json` に集約する
- 統計 pass した route だけで、その週の最終 `selection.trade_routes` を再生成する

出力:

- `weekly_revalidation_report.json`
- `candidate_report.json`
- `timeframe_comparison_summary.json`
- `statistical_qualification/*`
- `feature_drift_report.json`

統計 gate mode:

- `STATISTICAL_GATE_MODE=soft`
  - 検証フェーズ用
  - route は残し、`statistical_status` を診断ラベルとして使う
- `STATISTICAL_GATE_MODE=hard`
  - 本番候補審査用
  - 統計 fail route を `selection.trade_routes` から外す

既定は `soft`。

並列の既定:

- `WEEKLY_SCAN_PARALLEL=4`
  - weekly 本体の `market/limit/range probe` 比較
- `WEEKLY_ROUTE_PARALLEL=4`
  - manifest route の外側並列
- `WEEKLY_ROUTE_DATA_PARALLEL=1`
  - 各 route の `timeframe_comparison.sh` 内部並列

運用上は、まず route 側だけを 4 並列にし、各 route 内のデータ処理は 1 のまま固定する。

## なぜ 2 段階を残すのか

手動実行を 2 回に分ける必要はない。
ただし、ロジック上は 2 段階を残す意味がある。

- `autotune` は「良い route / 良い設定を探す」処理
- `weekly revalidation` は「その週の監査証跡を残す」処理

重複して見える部分はあるが、現時点で weekly 側には次が残っている。

- statistical qualification
- drift report
- fail-closed の週次レポート化
- tuned manifest を seed にした最終週次 selection の再生成

したがって、正式運用では「別々に手で回す」のではなく、
「1 本の orchestration で順番に回す」があるべき姿とする。

## 正式運用コマンド

```bash
RUN_ROOT=data/validation/weekly_autotune \
./scripts/weekly_autotune_pipeline.sh
```

このコマンドでは、`ROUTE_SELECTION_PATH` を手で付ける必要はない。
pipeline が直前に生成した manifest を、内部で `weekly revalidation` に自動で渡す。

`ROUTE_SELECTION_PATH=... ./scripts/weekly_strategy_revalidation.sh` が必要なのは、
`weekly_strategy_revalidation.sh` を単独で手動実行するときだけである。

既存 manifest を使って weekly だけ再実行したい場合は、次でよい。

```bash
RUN_ROOT=data/validation/weekly_autotune \
RUN_EXPANSION=0 \
RUN_REFINEMENT=0 \
RUN_WEEKLY=1 \
./scripts/weekly_autotune_pipeline.sh
```

この場合、pipeline は `manifest/route_selection_manifest.json` を再利用して weekly だけ実行する。

この 1 コマンドで次を順に行う。

1. `autotune expansion`
2. `autotune core_refinement`
3. manifest 生成と統合
4. `weekly revalidation`

## ディレクトリ構成

```text
data/validation/weekly_autotune/
  autotune_expansion/
  core_refinement/
  manifest/
  route_selection_runtime.env
  weekly_revalidation/
  pipeline_summary.json
  pipeline_summary.md
```

### `autotune_expansion/`

- 新規 core 候補探索の結果

### `core_refinement/`

- baseline core の再調整結果

### `manifest/`

- weekly 前の tuned seed manifest を集約する場所
- 想定ファイル:
  - `route_selection_manifest.json`
  - `route_selection_manifest.md`

### `route_selection_runtime.env`

- pipeline の current runtime 設定
- worker / systemd / 手動起動で共通に使う current env

`route_selection_runtime.env` は pipeline の current runtime 設定であり、
`RUN_WEEKLY=1` 後は `ROUTE_SELECTION_PATH` / `WEEKLY_REVALIDATION_REPORT_PATH` が
`weekly_revalidation_report.json` を指す。

`pipeline_summary.json/md` には、その run が `soft` / `hard` のどちらで週次統計 gate を扱ったかを
`statistical_gate_mode` として残す。

### `weekly_revalidation/`

- 週次監査レポート一式
- `RUN_WEEKLY=1` のときは、この配下の `weekly_revalidation_report.json` が runtime 正本になる

## manifest の扱い

### Delta manifest

- `autotune_route_manifest.json`
- 各 autotune run で新たに選ばれた route 差分

### Full manifest

- `autotune_full_route_manifest.json`
- weekly 前の統合 tuned route seed

### refinement 時の上書きルール

- `core_refinement` は baseline core と同一 route key を上書きしてよい
- ただし `expansion` で追加された新規 core は落としてはいけない
- そのため、refinement の full manifest 生成時は baseline candidate report ではなく
  `expansion` full manifest を seed としてマージ可能にする

## 現時点の制約

- route ごとに個別 `timeframe_comparison.sh` を回すため、manifest seed ありの weekly は従来 baseline より重い
- `limit` 側はまだ tuned manifest route を本線としては再評価していない
- `RUN_WEEKLY=0` の軽量実行では runtime 正本は `manifest/route_selection_manifest.json` のままになる
- `RUN_WEEKLY=1` の正式運用では runtime 正本は `weekly_revalidation_report.json` へ切り替わる

## 今回の実装対象

- 1 本の orchestration script を追加する
- 成果物を run root に集約する
- `core_refinement` が `expansion` の追加 core を落とさないよう full manifest merge を拡張する
- runtime 用 `ROUTE_SELECTION_PATH` を 1 箇所に固定しやすい env 出力を作る
- pipeline 完了後は、その env の `ROUTE_SELECTION_PATH` を weekly 正本へ自動で切り替える

## 今回あえてやらないこと

- weekly 側を manifest-aware な tuned route validator に全面改修すること
- `weekly_revalidation_report.json` を runtime 正本へ完全統合すること
- 過去 run の自動アーカイブ戦略

# プロジェクト横断レビュー結果

- Date: 2026-06-13
- Timezone: Asia/Tokyo
- Scope: プロジェクト進捗、主要機能、週次再検証、運用安全性、品質ゲート
- Reviewer: Codex
- Review type: 本日時点のコード・成果物・ドキュメント横断レビュー

## 結論

Phase 0-29 の主要機能、品質ゲート、運用自動化、検証レポート生成基盤は広く実装されている。
静的品質とテストは良好だが、Production向けの統計昇格条件と live execution の安全境界に重大な残件がある。

2026-06-13 時点の推奨判定は次のとおり。

- Futures Testnet / dry-run: 継続可能
- Production Go-Live: No-Go
- 実装進捗の目安: 85-90%
- 本番運用準備状況: Production統計ゲートと execution 整合性の是正待ち

## 環境別の統計ゲート方針

2026-06-13 の運用判断として、統計ゲートは環境別に次のように扱う。

| 環境 | 統計ゲート | 目的 |
|---|---|---|
| dry-run | soft / 観測用 | シグナル、route、risk、execution導線の機能確認 |
| Futures Testnet | soft / 警告付き試行可 | 実注文、約定、position、運用手順、障害復旧の検証 |
| Production | hard / fail-closed | statistical qualificationを通過したrouteだけを取引対象とする |

Testnetでは統計失格routeの試行を許可する。ただし、統計状態を隠さず、GUI・ログ・成果物で
`test-only / statistical-fail` と識別可能にする。Productionでは統計fail/missing routeを必ず拒否する。

## 本日確認した品質ゲート

| 項目 | 結果 |
|---|---|
| `ruff check .` | pass |
| `mypy src`（strict） | pass |
| `pytest -q` | 239 passed |
| `pytest -q -m smoke` | 18 passed |
| `scripts/validate_required_checks.py` | pass |
| Git worktree（レビュー開始時） | clean |

## 最新の週次再検証結果

参照成果物:

- `data/validation/weekly_autotune/weekly_revalidation/weekly_revalidation_report.json`
- `data/validation/weekly_autotune/weekly_revalidation/manifest_vs_weekly_diff.md`
- `data/validation/weekly_autotune/weekly_revalidation/statistical_fail_diagnostics.md`
- `data/validation/weekly_autotune/manifest/route_selection_manifest.md`

確認結果:

- weekly revalidation の総合状態は `warn`
- market の point estimate 条件は `pass`
- statistical qualification は対象6ルートすべて `fail`
- manifest と weekly rerun の point metric は6ルートすべて一致
- manifest 採用時より weekly の fold OOS 窓は広がったが、trade OOS の実サンプルは増えていない
- runtime env は statistical fail route を含む4 symbol / 6 route を有効化している

主要な失格例:

| Route | 分類 | 主な問題 |
|---|---|---|
| `trend:SOLUSDT:15m` | `oos_quality` | PF 0.504、期待値 -13.98bps、最終OOS PnLマイナス |
| `range:SOLUSDT:30m` | OOS品質悪化 | 最終fold PF 0.712、期待値 -15.76bps |
| `trend:ADAUSDT:30m` | `sample_thin` | closed trades 16、CI下限と損失確率が未達 |
| `trend:BNBUSDT:1h` | `sample_thin` | closed trades 7、fold間変動が大きい |
| `trend:ADAUSDT:1h` | sample不足 | 最終OOS closed trades 6 |
| `trend:ETHUSDT:1h` | OOS品質悪化 / sample不足 | 最終fold PF 0.082、closed trades 5 |

## 重要なレビュー指摘

### P0: Production向け統計ゲートの環境境界が未実装

事実:

- `weekly_autotune_pipeline.sh` と `weekly_strategy_revalidation.sh` の既定は
  `STATISTICAL_GATE_MODE=soft`
- soft mode では statistical fail route も `selection.trade_routes` に残り、Testnet試行に利用できる
- worker は `selection.trade_routes` が存在すると、各 route の `statistical_status` を検査せず採用する
- 現在の `route_selection_runtime.env` は全6 statistical fail route を指す週次レポートを正本としている

影響:

- Testnet試行としては許容できるが、worker自身はTestnetとProductionを区別していない
- Production起動時に同じroute正本を参照すると、統計fail routeが注文対象になり得る
- Productionのfail-closed方針をコード上で保証できていない

必要な対応:

- workerに明示的な実行環境または統計ゲートモードを持たせる
- Productionでは `statistical_status=pass` 以外をworker側でも拒否する
- Testnetではfail routeを許可するが、`test-only / statistical-fail` をログとGUIに表示する
- Production用runtime成果物は `hard` gate、Testnet用runtime成果物は `soft` gateとして分離する

### P0: 注文 ACK を約定として position に即時反映している

事実:

- worker は gateway の `ack` を受けた時点で `FillEvent` を生成し position を更新する
- Binance の `accepted:NEW` は注文受付であり、約定完了を意味しない
- execution reconciliation は `filled/canceled/expired` を扱うが、`partial` を無視する

影響:

- 未約定または部分約定の注文を全量約定として扱う可能性がある
- local position、取引所 position、risk exposure が一時的または恒久的に不一致になる

必要な対応:

- ACK 時は pending order のみ永続化する
- position 更新は execution report の累積約定数量・実約定価格を正本にする
- partial fill、重複イベント、順序逆転、再起動後の reconciliation をテストする

### P1: production risk config と live worker の制限値が一致しない

事実:

- `config/config.prod.yaml`: symbol exposure 8%、portfolio exposure 25%
- worker CLI / PositionManager の既定: symbol exposure 25%、portfolio exposure 70%
- live worker は `RiskManager` の DD、相関、ボラ加重、risk contribution 制御を注文前に使用していない

影響:

- production 設定より緩い exposure 制限で worker が動作する可能性がある
- `risk first` 方針と実際の live order gate が一致しない

必要な対応:

- production config を worker / risk / exchange の単一正本にする
- 注文直前に DD、symbol、portfolio、correlation、volatility の全 gate を評価する
- 起動時に有効設定値を構造化ログと GUI に表示する

### P1: runtime state 消失時に gateway が fail-open

事実:

- gateway は runtime state path 未指定、またはファイル不存在時に注文を許可する
- exchange CLI の `--runtime-state-path` 既定値は `None`
- invalid JSON は拒否するが、missing state は拒否しない

影響:

- state file の削除、mount不良、引数漏れで runtime gate を迂回できる

必要な対応:

- testnet-live / production は state 未指定・不存在・期限切れを拒否する
- dry-run のみ明示オプションで fail-open を許可する
- state freshness の最大許容時間を設定する

### P1: Go-Live 判定の正本が最新成果物を参照していない

事実:

- `update_go_live_checklist.sh` の既定は旧パス
  `data/validation/weekly_revalidation/weekly_revalidation_report.json`
- 正式運用の正本は
  `data/validation/weekly_autotune/weekly_revalidation/weekly_revalidation_report.json`
- Go-Live checklist は `weekly_status=pass` / `statistical_status=missing` を表示しており、
  最新正本の `weekly=warn` / `statistical=fail` と一致しない

影響:

- 運用者が古い判定を最新判定として読む可能性がある

必要な対応:

- pipeline summary または runtime env から正本パスを解決する
- レポートに run ID、generated_at、input path を表示する
- stale report を No-Go とする

## 機能別レビュー

| 機能 | 進捗評価 | 本日時点の課題 |
|---|---|---|
| データ取得 / OHLCV | 良好 | gap修復済み。coverage確認の定期自動化が必要 |
| Feature Engine | 良好 | backtest と live の特徴量同一性を継続検証する |
| Regime Classifier | 良好 | regime変化時の戦略停止・切替のlive証跡を増やす |
| Range Strategy | 要改善 | SOL 30m の最終OOS品質悪化。XRP等の再探索が必要 |
| Trend Strategy | 要改善 | SOL 15m はOOS品質失敗。他候補は主にsample不足 |
| ML Pipeline | 基盤実装済み | artifact freshness、失敗時方針、live効果測定が必要 |
| Backtest / Walkforward | 良好 | limitモデルと実約定差分、複数route portfolio評価を強化する |
| Statistical Qualification | 良好 | Production経路へ強制適用し、Testnetでは警告として扱う |
| Risk Management | 要改善 | production設定との統合、全risk gateのlive適用が必要 |
| Exchange Gateway | 要改善 | runtime missing fail-open、timeout後照会、ACK/fill分離が必要 |
| Position Management | 要改善 | execution report正本化とpartial fill整合が必要 |
| Worker | 要改善 | 1,000行超の責務集中。route/execution/order/signalを分割する |
| Runtime / State durability | 良好 | state freshness、stale lock回収、missing state拒否を追加する |
| GUI | 良好 | statistical fail routeをTestnet試行中、Production取引不可として表示する |
| Ops / Notify / Monitor | 良好 | production投入前のend-to-endアラート証跡が必要 |
| CI / Tests | 良好 | coverage計測、live safety regression suiteを追加する |
| Documentation | 要整理 | README、TASKS、Go-Live checklist、最新成果物の進捗表現を同期する |

## AIが洗い出した今後の課題

以下は、コード、テスト、運用ドキュメント、最新検証成果物を横断してAIが抽出した課題である。

### 最優先: Production安全境界

| ID | 項目 | 内容 | 完了条件 |
|---|---|---|---|
| AI-001 | 環境別統計ゲート | Testnetはsoft、Productionはhardに固定する | 同じfail routeがTestnetでは許可、Productionでは拒否される |
| AI-002 | Productionの二重統計ゲート | Production workerで `statistical_status=pass` を必須化 | Productionでfail/missing route拒否テストがpass |
| AI-003 | ACKとfillの分離 | ACKではpositionを更新せずpending orderとして管理 | NEW→FILLED/PARTIAL/CANCELEDの全遷移テストがpass |
| AI-004 | execution reconciliation強化 | partial、重複、順序逆転、再起動を処理 | 取引所event再生後にposition/order stateが一致 |
| AI-005 | runtime state fail-closed | missing/invalid/stale stateで注文拒否 | live modeで全欠損ケースが拒否される |
| AI-006 | production risk設定統合 | prod YAMLをworkerの有効risk設定へ反映 | 8%/25%制限がworker統合テストで確認できる |
| AI-007 | full live risk gate | DD、相関、ボラ加重、risk contributionを注文前評価 | 各risk理由で発注拒否するE2Eテストがpass |

### 高優先: Go-Live判定と証跡

| ID | 項目 | 内容 | 完了条件 |
|---|---|---|---|
| AI-008 | Go-Live正本パス統一 | checklist更新処理をweekly autotune正本へ追従させる | 最新weekly warn/stat failがchecklistへ反映される |
| AI-009 | artifact run ID導入 | 同一runのreport/diagnostics/manifestを識別する | 全成果物に共通run IDとgenerated_atがある |
| AI-010 | stale artifact gate | 古いweekly/statistical/healthレポートを拒否する | 許容期間超過時にGo-Live判定がNo-Go |
| AI-011 | diagnostic completeness | statistical fail全routeを診断レポートへ掲載する | failed route数とdiagnostics route数が一致 |
| AI-012 | route-centric longrun再取得 | statistical failを許容した現行workerで8h longrunとFutures Testnetを再実施 | test-only表示とposition/order/route key整合の証跡が残る |

### 高優先: 戦略品質

| ID | 項目 | 内容 | 完了条件 |
|---|---|---|---|
| AI-013 | SOL trend本番候補降格 | `trend:SOLUSDT:15m` をProduction候補から除外し、Testnetで原因分析 | 最終OOS失敗が再現・説明される |
| AI-014 | SOL range再評価 | `range:SOLUSDT:30m` のfold 1-3悪化を分析 | neighboring parameter比較と降格判断を記録 |
| AI-015 | sample thin候補の扱い | ADA/BNB/ETH routeは再調整よりOOS蓄積を優先 | route 30件・strategy 100件条件を満たす |
| AI-016 | portfolio-level qualification | route単体だけでなく同時運用時のDD/相関を評価 | 候補portfolioが統計・risk基準をpass |
| AI-017 | selection bias監査 | autotuneと最終OOSの分離を強化する | tuningに未使用の最終holdoutで再評価 |

進捗メモ:
- `route_quality_audit` は `sample_thin` と `oos_quality` を分離し、route ごとに `accumulate_oos` / `drop_or_retune` を返す。
- `route_quality_summary` と `strategy_quality_summary` を追加し、`trend` / `range` の優先度を運用成果物へ出力した。
- `portfolio_qualification.strategy_breakdown` を追加し、bundle 内の strategy 別に selected / qualified route 数を追えるようにした。
- `pipeline_summary.json` の `runtime_options` で `soft` / `hard` を分離済みで、`route_selection_runtime.testnet.env` と `route_selection_runtime.production.env` からも両方追える。
- 2026-06-14 時点で longrun 実行は完了済みで、最新の証跡は `docs/implementation/longrun-validation-record-2026-06-14.md` と `data/validation/futures_runtime_gate_check.jsonl` にまとまっている。
- `strategy_quality_summary` と `selection_bias_final_holdout_strategy_summary` を `./scripts/strategy_quality_report.sh` で Markdown / JSON 出力できるようにし、AI-015〜017 の strategy 判定を運用入口から直接追えるようにした。
- `strategy_quality_report.md` に `Trade Coverage` を追加し、route / strategy の closed trades と `Gap To 30` / `Gap To 100` で OOS 蓄積の進捗を追えるようにした。
- `strategy_quality_report.md` に `Route Coverage` を追加し、route-level の accumulate / drop 順も追えるようにした。
- `tests/test_strategy_quality_report_script.py` で strategy 品質レポートの出力を固定し、運用入口の回帰をテスト化した。
- `update_go_live_checklist.sh` に `strategy_quality_report.md` / `strategy_quality_report.json` の参照を追加し、Go-Live 正本からも AI-015〜017 の結論を直接読めるようにした。
- `./scripts/ai_strategy_progress_report.sh` を追加し、AI-013〜017 の現在地を Markdown / JSON の1枚要約として読めるようにした。
- `weekly_autotune_pipeline.sh` から `ai_strategy_progress_report.md` / `ai_strategy_progress_report.json` を自動生成するようにし、進捗の正本を weekly_revalidation 配下に集約した。
- `ai_strategy_progress_report.md` に `Trade Coverage` を追加し、AI-015 の route 30件 / strategy 100件条件までの距離も見えるようにした。
- `ai_strategy_progress_report.md` に `Route Coverage` を追加し、AI-015 の route-level の next action も見えるようにした。
- `ai_strategy_progress_report.md` に `Pass Gaps` を追加し、AI-016 の portfolio-level 残差も見えるようにした。
- `portfolio_next_action_report.md` に `Qualification` / `pass_path` / `Route Coverage` を追加し、AI-016 の不足母集団と次の確認順を1枚で読めるようにした。
- AI-013〜017 の現在地は `data/validation/weekly_autotune/weekly_revalidation/ai_strategy_progress_report.md` を正本として読む。

- `weekly_revalidation_report.json` は単一 run の正本なので、その run で使った `statistical_gate_mode` だけを保持する。
- `portfolio_strategy_actions` を追加し、strategy 別の bundle pass / review を overview からも追えるようにした。
- `portfolio_strategy_priority_summary` を追加し、strategy 別に先に見る route を `priority_route_keys` で固定した。
- `route_priority_summary` を追加し、AI-013/014 の route 別確認順を `priority_route_keys` で固定した。
- `selection_bias_audit.final_holdout_audit.strategy_deltas` を追加し、holdout 差分を strategy 別に追えるようにした。
- `selection_bias_audit.final_holdout_summary.strategy_summary` を追加し、overview から strategy 別の holdout 平均差分を確認できるようにした。
- `overview.selection_bias_final_holdout_strategy_summary` を追加し、GUI / 運用面からも strategy 別 holdout summary を直接読めるようにした。
- `portfolio_qualification.status` は現週次で `fail` のままで、qualified route がまだ 0 件なので portfolio-level pass には未到達。
- `portfolio_qualification.missing_route_count` / `missing_strategy_count` を追加し、portfolio-level pass までの不足母数を定量化した。
- `overview.portfolio_qualification_summary.reasons` を追加し、portfolio-level fail の直接理由を overview から読めるようにした。
- `overview.portfolio_qualification_summary.selected_route_keys` / `qualified_route_keys` を追加し、overview から route 実体を直接追えるようにした。
- `overview.portfolio_qualification_summary.required_route_count` / `required_strategy_count` を追加し、portfolio-level pass の基準値を固定した。
- `overview.portfolio_qualification_gap_summary.next_route_keys` を追加し、次に見る route 順も overview から直接読めるようにした。
- `overview.portfolio_next_action_summary` を追加し、strategy 別の accumulate_oos / drop_or_retune の実体を overview から読めるようにした。
- `overview.portfolio_next_action_summary.*.accumulate_oos_route_keys` / `drop_or_retune_route_keys` を追加し、次に増やす/切る route を overview から直接読めるようにした。
- `overview.portfolio_next_action_route_keys` を追加し、portfolio-level の次アクション順を1本で読めるようにした。
- `./scripts/portfolio_next_action_report.sh` を追加し、portfolio-level next action を Markdown で出せるようにした。
- `weekly_autotune_pipeline.sh` で `portfolio_next_action_report.md` を weekly_revalidation 配下へ自動生成するようにした。
- 現週次の next action は `trend:ADAUSDT:1h`, `trend:ADAUSDT:30m`, `trend:BNBUSDT:1h`, `trend:ETHUSDT:1h` を `accumulate_oos`、`trend:SOLUSDT:15m` と `range:SOLUSDT:30m` を `drop_or_retune` として扱う。
- 現週次の `portfolio_next_action_route_keys` は `trend:ADAUSDT:1h`, `trend:ADAUSDT:30m`, `trend:BNBUSDT:1h`, `trend:ETHUSDT:1h`, `range:SOLUSDT:30m`, `trend:SOLUSDT:15m` の順。
- 現週次の selected route は `range:SOLUSDT:30m`, `trend:ADAUSDT:1h`, `trend:ADAUSDT:30m`, `trend:BNBUSDT:1h`, `trend:ETHUSDT:1h`, `trend:SOLUSDT:15m` の 6 件。
- `portfolio_qualification` の不足母数は route 6 件、strategy 2 件で、まずは 2 strategy 以上の qualified route を 2 件以上作る必要がある。
- 現在の週次結果では、`trend:ADAUSDT:1h`, `trend:ADAUSDT:30m`, `trend:BNBUSDT:1h`, `trend:ETHUSDT:1h`, `range:SOLUSDT:30m`, `trend:SOLUSDT:15m` の順で見る。
- `trend:SOLUSDT:15m` と `range:SOLUSDT:30m` は現週次で `drop_or_retune` 判定のまま残る。
- `route_selection_runtime.production.env` は hard-gated selection を参照し、Testnet 用 runtime と分離済み。
- 残作業は、holdout 固定の比較証跡を定常更新しつつ、strategy / portfolio-level の再評価を積むこと。

現週次の AI-013〜017 進捗は `data/validation/weekly_autotune/weekly_revalidation/ai_strategy_progress_report.md` を参照する。本文の進捗表はここでは持たず、正本を 1 つに集約する。

### 中優先: 実装品質と保守性

| ID | 項目 | 内容 | 完了条件 |
|---|---|---|---|
| AI-018 | worker責務分割 | route sync、signal、execution、order、stateを分割 | 各モジュールの単体テストと明確なI/O契約がある |
| AI-019 | config単一正本化 | YAML、CLI default、envの優先順位を統一 | effective configを1か所で生成・表示できる |
| AI-020 | coverage gate導入 | pytest coverageをCI required checkへ追加 | safety-critical moduleの最低coverageを固定 |
| AI-021 | live safety regression suite | fail-open、duplicate、stale、partial等をまとめる | CIで専用suiteが毎回実行される |
| AI-022 | structured error logging | 広い `except Exception` の握り潰しを減らす | safety-critical例外にreason/path/contextが残る |
| AI-023 | stale lock recovery | PID/ageを用いたlock回収方針を追加 | crash後の自動復旧テストがpass |

### 中優先: Executionモデルと運用

| ID | 項目 | 内容 | 完了条件 |
|---|---|---|---|
| AI-024 | timeout後のorder照会 | retry前にclient order IDで状態照会する | timeout後の重複注文が発生しない |
| AI-025 | limit queue aging / GTC近似 | Phase 27残件を実装する | backtestとtestnetのfill率差を評価できる |
| AI-026 | 銘柄別execution profile | depth/queue/slippageをsymbol別に設定 | 実績から定期更新できる |
| AI-027 | live/backtest差分監視 | fill、slippage、latency、reject率を比較 | 乖離閾値超過で自動警告される |
| AI-028 | order/position照合ジョブ | 定期的に取引所正本とlocal stateを照合する | 不一致検出時に新規注文停止と通知が行われる |

### 低〜中優先: ドキュメントと進捗管理

| ID | 項目 | 内容 | 完了条件 |
|---|---|---|---|
| AI-029 | `TASKS.md`更新 | 全項目未完了表記を現状に同期する | README/checklist/TASKSの進捗が一致 |
| AI-030 | Go-Live表現整理 | Conditional Go履歴と最新No-Goを明確に分ける | 最新判定を誤読できない構成になる |
| AI-031 | 実行時間予算管理 | weekly/autotune/cost-gridのTATを監視する | ジョブ別SLOと超過警告がある |
| AI-032 | data retention方針 | 12GB超のdata成果物をrun単位で整理する | retention/archive/削除基準が文書化される |

## 推奨実施順

1. `AI-001` から `AI-007` を修正し、Productionはfail-closed、Testnetは警告付き試行可能にする。
2. `AI-008` から `AI-012` でGo-Live判定と証跡の正本を統一する。
3. Testnetで統計失格routeを含むFutures Testnetと8h longrunを実施し、executionと運用安全性を検証する。
4. `AI-013` から `AI-017` の戦略品質改善とOOS蓄積を進める。
5. 保守性、execution精度、ドキュメント整合を継続改善する。

## Go-Live再判定条件

次をすべて満たすまでProduction Go-LiveはNo-Goとする。

- Production runtime正本に statistical fail/missing route が含まれない
- Production workerが fail/missing route を独立して拒否する
- ACKとfillが分離され、execution report後にpositionが一致する
- production risk設定がlive workerへ反映される
- runtime state missing/invalid/staleがfail-closedになる
- route-centric worker変更後のFutures Testnetと8h longrun証跡がある
- route・strategy・portfolioの統計qualificationがpassする
- 最新成果物を参照したGo-Live checklistが `go_live_ready=true` になる

## 参照コード・ドキュメント

- `src/auto_trader/analysis/trade_routes.py`
- `src/auto_trader/worker/runner.py`
- `src/auto_trader/worker/cli.py`
- `src/auto_trader/exchange/gateway.py`
- `src/auto_trader/position/manager.py`
- `config/config.prod.yaml`
- `scripts/weekly_autotune_pipeline.sh`
- `scripts/weekly_strategy_revalidation.sh`
- `scripts/update_go_live_checklist.sh`
- `docs/implementation/weekly-revalidation-operations.md`
- `docs/implementation/trading-go-live-checklist.md`

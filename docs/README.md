# ドキュメント運用ガイド（Phase 0-29）

## 目的
この `docs/` は、`base_policy.md` を実装可能な仕様に落とすための設計基盤です。
本プロジェクトは **ADR（意思決定）** と **Spec（実装仕様）** を分離して管理します。

## 参照順（必須）
1. `base_policy.md`（上位方針）
2. `docs/adr/`（なぜその設計にしたか）
3. `docs/specs/`（どう実装するか）
4. `docs/implementation/`（実装順・Done定義・検証観点）

## ディレクトリ構成
- `docs/adr/`: Architecture Decision Records
- `docs/specs/`: Phase別の実装仕様（Phase 0-29）
- `docs/implementation/`: 実装チェックリスト、テスト戦略、リスク登録簿

## 標準運用フロー（Phase 25+）
1. `docs/specs/` の対象Phase Specを更新または追加する。
2. `docs/implementation/` に `spec-review-phaseXX-YYYY-MM-DD.md` を作成する。
3. `docs/implementation/phaseXX-implementation-checklist.md` を更新する。
4. 証跡スクリプトを実行する。
   - 週次再評価（定期実行）: `./scripts/weekly_strategy_revalidation_with_core.sh`
   - 週次再評価（手動本線）: `./scripts/weekly_strategy_revalidation.sh`
   - 自動売買対象の daily backtest: `./scripts/backtest_symbol_rotation.sh`
   - longrun / health: `./scripts/longrun_8h_check.sh` または既存証跡確認
5. `./scripts/update_go_live_checklist.sh` を実行し、Auto判定欄を同期する。
6. `docs/implementation/trading-go-live-checklist.md` で最終判定（Go/Conditional/No-Go）を確定する。

## 運用ランブック
- runtime / worker / monitor / risk の常駐・定期運用: `docs/implementation/runtime-control-operations.md`
- 週次戦略再評価（定期実行は `./scripts/weekly_strategy_revalidation_with_core.sh`、手動本線は `./scripts/weekly_strategy_revalidation.sh`）: `docs/implementation/weekly-revalidation-operations.md`
- ライブ監視コンソール: `src/auto_trader/gui/app.py` の `Overview / Trading / Analysis` タブ

## 最新のプロジェクト横断レビュー
- 2026-06-13: `docs/implementation/project-review-2026-06-13.md`

## Doc First ルール（必須）
- 実装開始前に、対象PhaseのSpecを `docs/specs/` に追加または更新する。
- Specに未記載のI/O契約はコードへ持ち込まない。
- 実装中に設計変更が発生した場合、先にSpec/ADRを更新してからコード変更する。
- `spec-review` が未作成のPhaseは、コミット前にレビュー結果を `docs/implementation/` に残す。

## ADR ルール
- 命名: `NNNN-title.md`（4桁連番）
- 状態: `Proposed | Accepted | Superseded`
- 置換時:
  - 新ADRを追加し `Supersedes` / `Superseded by` を相互記載
  - 旧ADRは削除せず `Superseded` に変更
- 1 ADR 1 判断（判断粒度を混在させない）

## Spec ルール
各Specは以下セクションを必須とします。
- 目的
- 入力（I/O 契約）
- 出力（I/O 契約）
- 前提条件
- 失敗モードと対策
- テスト観点

## 変更管理ルール
- 方針変更は先にADRを更新し、その後Specを更新する。
- Spec更新時は関連ADR番号を必ず追記する。
- `base_policy.md` と矛盾する変更は禁止。必要なら先に方針提案を作成する。

## 言語ポリシー
- 本プロジェクト文書は原則日本語で記述する。
- 外部ライブラリ固有語は英語併記を許可する。

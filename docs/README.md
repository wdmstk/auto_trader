# ドキュメント運用ガイド（Phase 0-17）

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
- `docs/specs/`: Phase別の実装仕様（Phase 0-17）
- `docs/implementation/`: 実装チェックリスト、テスト戦略、リスク登録簿

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

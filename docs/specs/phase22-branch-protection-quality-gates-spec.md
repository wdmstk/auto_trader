# Phase 22 Spec: Branch Protection Quality Gates

- Version: 1.0
- Date: 2026-05-31
- Related ADR: 0001, 0002

## 目的
`main` ブランチへの品質担保を強制するため、required checks を定義し、設定ドリフトを検知可能にする。

## 入力（I/O契約）
- CI workflow 定義（`.github/workflows/ci.yml`）
- 保護対象ブランチ（`main`）

## 出力（I/O契約）
- required checks 定義文書
- required checks 検証結果（pass/fail）

## 前提条件
- 必須チェックは `full` と `smoke` の2系統を維持する。
- required checks 名変更時は、文書と検証ロジックを同時更新する。

## 仕様
1. required checks
- `full`
- `smoke`

2. 保護ルール
- required checks 成功前は `main` への merge を禁止。
- 直pushは禁止（PR経由）。

3. ドリフト検知
- workflow 内に required checks が存在することを検証する。
- 欠落時はCI失敗にする。

## 失敗モードと対策
- ジョブ名変更漏れ: 検証スクリプトで検知。
- ブランチ保護設定漏れ: Runbookの設定手順で再確認。

## テスト観点
- required checks が workflow に存在すること。
- required checks 欠落時に検証が fail すること。

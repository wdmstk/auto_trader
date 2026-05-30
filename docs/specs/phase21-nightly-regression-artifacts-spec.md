# Phase 21 Spec: Nightly Full Regression and Artifacts

- Version: 1.0
- Date: 2026-05-31
- Related ADR: 0001, 0002, 0003

## 目的
日次で full 回帰を自動実行し、smoke/full のテスト結果をアーティファクトとして保存して追跡性を高める。

## 入力（I/O契約）
- テストスイート（smoke/full）
- CI実行環境（GitHub Actions）

## 出力（I/O契約）
- `smoke-report.xml`
- `full-report.xml`
- CIアーティファクト（workflow run単位）

## 前提条件
- smoke は PR/Push で実行継続。
- full は PR/Pushに加えて nightly で実行。
- レポートは失敗時も保存する。

## 仕様
1. トリガー
- `pull_request`
- `push`（main）
- `schedule`（daily）

2. レポート
- smoke: `pytest -q -m smoke --junitxml=smoke-report.xml`
- full: `pytest -q --junitxml=full-report.xml`

3. アーティファクト
- smoke/full 各レポートを upload-artifact で保存。
- retention を明示設定する。

## 失敗モードと対策
- レポート未生成: upload step は `if: always()` で実行。
- nightly失敗見逃し: workflow通知（GitHub標準通知）を活用。

## テスト観点
- nightly トリガー構文が有効であること。
- smoke/full のXMLレポートが生成されること。
- 失敗時でもレポートが保存されること。

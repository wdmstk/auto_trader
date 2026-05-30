# Phase 20 Spec: Test Profile Separation (smoke/full)

- Version: 1.0
- Date: 2026-05-31
- Related ADR: 0001, 0002, 0003

## 目的
テスト実行を `smoke` と `full` に分離し、日常の変更検証を高速化しつつ回帰網羅性を維持する。

## 入力（I/O契約）
- テストスイート（`tests/`）
- pytest 設定（marker）
- CI ワークフロー

## 出力（I/O契約）
- `smoke` 実行コマンド
- `full` 実行コマンド
- CIジョブ（smoke/fullの分離）

## 前提条件
- `smoke` は5分以内目安の軽量セット。
- `full` は全テスト回帰を対象。
- `smoke` は安全ゲート（risk/runtime/HIGH_VOL/e2e）を必ず含む。

## 仕様
1. マーカー
- `@pytest.mark.smoke` を導入。
- `smoke` はマーカー付きテストのみ実行。

2. 実行コマンド
- smoke: `pytest -q -m smoke`
- full: `pytest -q`

3. CI分離
- `smoke` ジョブ: PR/Push で常時実行。
- `full` ジョブ: PR/Push で実行（将来はnightly分離可能）。

## 失敗モードと対策
- smoke過小: 重要導線漏れをレビュー観点で防止。
- smoke過大: 実行時間閾値を越える場合は削減。
- マーカー漏れ: 新規重要テスト追加時にsmoke含有を確認。

## テスト観点
- `pytest -m smoke` が動作すること。
- `smoke` に e2e/risk/runtime/orchestrator 主要検証が含まれること。
- CIで smoke/full が分離実行されること。

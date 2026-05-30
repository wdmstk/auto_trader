# Phase 18 Spec: CI Smoke Automation

- Version: 1.0
- Date: 2026-05-31
- Related ADR: 0001, 0002, 0003

## 目的
Phase 17 の E2E スモークをCIで自動実行し、PR/commit時にフェーズ間接続不整合を早期検知する。

## 入力（I/O契約）
- リポジトリソース
- テスト依存環境（Python 3.12）
- スモーク入力フィクスチャ（テスト内生成）

## 出力（I/O契約）
- CI結果（pass/fail）
- スモークテストログ

## 前提条件
- スモークは dry-run 専用で外部取引所へ接続しない。
- 失敗時は merge を止める品質ゲートとして扱う。

## 仕様
1. トリガー
- `push`（`main`）
- `pull_request`

2. ジョブ
- `smoke`: Phase 17 のスモークテストを最小セットで実行
- `quality`: `ruff`, `mypy`, `pytest -q` の基本品質ゲート

3. 実行順
- `smoke` は独立ジョブで実行可能。
- `quality` 失敗時も `smoke` 結果は確認可能にする（並列実行）。

## 失敗モードと対策
- 依存取得失敗: pipキャッシュ利用で軽減。
- テスト不安定: 入力固定・時刻固定で再現性を確保。
- 長時間化: smokeを軽量ケースに限定する。

## テスト観点
- Workflow構文が正しいこと。
- `tests/test_e2e_smoke.py` がCI上で実行されること。
- CI失敗時に失敗ステージ情報がログで確認できること。

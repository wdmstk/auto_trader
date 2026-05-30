# Phase 23 Spec: CI Policy Drift Guard

- Version: 1.0
- Date: 2026-05-31
- Related ADR: 0001, 0002

## 目的
required checks 定義のドリフトをCIで自動検知し、運用設定の破綻を未然に防ぐ。

## 入力（I/O契約）
- `.github/workflows/ci.yml`
- `scripts/validate_required_checks.py`

## 出力（I/O契約）
- `validate-gates` ジョブの pass/fail

## 前提条件
- required checks は `full`, `smoke`。

## 仕様
1. CIに `validate-gates` ジョブを追加。
2. ジョブは `python scripts/validate_required_checks.py` を実行。
3. 欠落時はCI失敗。

## テスト観点
- required checks が揃っていれば pass。
- 欠落時は fail。

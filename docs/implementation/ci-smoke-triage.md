# CI/Smoke 失敗時トリアージ

## 目的
CI（quality/smoke）失敗時に、最短で原因特定するための確認順を定義する。

## 確認順
1. `quality` と `smoke` のどちらが失敗したか確認
2. 失敗ジョブ内の最初の失敗ステップを確認
3. ローカルで同じコマンドを再実行
4. artifact（`smoke-report.xml`, `full-report.xml`）を取得して失敗ケースを特定

## quality 失敗
- `ruff check .`
- `mypy src`
- `pytest -q`

上から順に修正し、再実行する。

## smoke 失敗
- `pytest -q tests/test_e2e_smoke.py`
- `python -m auto_trader.e2e ...` 実行で `overall_status` と stage error を確認

## nightly 失敗
- `schedule` 実行runの `full-report.xml` と `smoke-report.xml` を確認
- 同じコミットでローカル再実行:
  - `pytest -q -m smoke`
  - `pytest -q`

## よくある原因
- スキーマ変更で `signal/risk/runtime` 契約が崩れた
- order gate 条件（HIGH_VOL/risk/runtime/pass_filter）が変更された
- 生成ファイルパス変更がテストに反映されていない

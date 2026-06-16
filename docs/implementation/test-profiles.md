# テストプロファイル運用（Phase 20）

## プロファイル
1. smoke
- 目的: 主要安全ゲートと横断導線の高速確認
- コマンド: `pytest -q -m smoke`

2. full
- 目的: 全体回帰確認
- コマンド: `pytest -q`

## 使い分け
- 開発中: `smoke` を高頻度で実行
- マージ前/大きな変更: `full` を実行

## smoke対象の目安
- runtime gate
- risk manager
- e2e smoke
- dry-run orchestrator
- live safety regression suite (`tests/test_live_safety_regression.py`)

## 追加ルール
- 新規で安全ゲートに関わるテストは `@pytest.mark.smoke` を付与する。
- fail-open / duplicate / stale / partial の回帰は `tests/test_live_safety_regression.py` に集約する。

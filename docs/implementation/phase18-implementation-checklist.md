# Phase 18 実装チェックリスト（CI Smoke Automation）

## 実装項目
- [x] GitHub Actions workflow 作成
- [x] smokeジョブ作成（Phase 17）
- [x] qualityジョブ作成（ruff/mypy/pytest）
- [x] CI実行手順のREADME追記
- [x] 失敗時トリアージ手順のドキュメント化

## Done定義
- [x] PR作成時にsmokeが自動実行される
- [x] main push時にquality/smokeが実行される
- [x] 失敗ログから原因特定が可能
- [x] ローカル手順とCI手順の乖離がない

## レビュー観点
1. 外部依存なしで再現実行できること
2. 実行時間が過剰でないこと
3. スモーク対象が安全ゲートをカバーしていること

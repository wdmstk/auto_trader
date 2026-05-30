# Phase 19 実装チェックリスト（Dry-Run Orchestrator）

## 実装項目
- [x] orchestratorモジュール作成
- [x] dry-run CLI実装
- [x] e2e/ops/notify の順次実行実装
- [x] step別レポート保存実装
- [x] fail-fast制御実装
- [x] README実行手順追記

## Done定義
- [x] ワンコマンドで事前確認が完了する
- [x] 失敗stepが明示される
- [x] notify未設定時のskipが明示される
- [x] dry-runで外部発注しない
- [x] ユニット/統合テストが通る

## レビュー観点
1. 本番系コマンドと誤用されない設計か
2. 失敗時の原因がレポートだけで追跡可能か
3. ステップ間契約が明示されているか

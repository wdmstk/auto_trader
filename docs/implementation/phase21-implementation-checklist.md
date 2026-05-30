# Phase 21 実装チェックリスト（Nightly Regression + Artifacts）

## 実装項目
- [x] CIに nightly schedule を追加
- [x] smoke/full junitxml 出力を追加
- [x] smoke/full レポートの artifact 保存を追加
- [x] README に運用説明を追記
- [x] 失敗時トリアージ手順を更新

## Done定義
- [x] nightly が自動実行される
- [x] smoke/full レポートが常時保存される
- [x] 失敗runでもレポート回収できる
- [x] 運用者が履歴比較できる

## レビュー観点
1. CI実行時間増加が許容範囲か
2. 失敗時可観測性が改善しているか
3. 手順が既存運用と矛盾しないか

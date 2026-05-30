# Phase 20 実装チェックリスト（Test Profile Separation）

## 実装項目
- [x] pytest marker（smoke）定義
- [x] 主要テストへ smoke マーク付与
- [x] CI workflow の smoke/full 分離
- [x] README に実行方法追記
- [x] テスト運用ガイド追記

## Done定義
- [x] `pytest -m smoke` が通る
- [x] `pytest`（full）が通る
- [x] CIで smoke/full が別ジョブで可視化される
- [x] smoke実行時間がfullより有意に短い

## レビュー観点
1. smokeが安全ゲートを十分カバーしていること
2. full回帰が失われていないこと
3. 開発者が迷わず使える運用導線になっていること

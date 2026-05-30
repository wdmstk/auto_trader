# Phase 22 実装チェックリスト（Branch Protection Quality Gates）

## 実装項目
- [x] required checks 定義ドキュメント作成
- [x] workflow required checks 検証スクリプト実装
- [x] 検証テスト追加
- [x] README/運用手順へ反映

## Done定義
- [x] required checks (`full`, `smoke`) が固定化される
- [x] 欠落時に自動検知できる
- [x] 手順に沿ってブランチ保護を設定できる

## レビュー観点
1. ルールと実装に矛盾がないこと
2. CI変更時に追従しやすいこと
3. 運用者が再設定しやすいこと

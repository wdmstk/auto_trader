# Phase 24 Spec: Operations Closeout (Notification Excluded)

- Version: 1.0
- Date: 2026-05-31
- Related ADR: 0001, 0002

## 目的
通知機能を除いた運用導線について、最終的な適用確認と完了判定を標準化する。

## 入力（I/O契約）
- Branch protection 設定状況
- CI 実行履歴（smoke/full/validate-gates）
- Runbook/手順ドキュメント

## 出力（I/O契約）
- 運用完了チェックリスト結果
- 未解決項目一覧（あれば）

## 前提条件
- 通知関連（Phase 15/16）は本フェーズ対象外。
- required checks は `full`, `smoke`, `validate-gates` を前提とする。

## 仕様
1. ブランチ保護確認
- `main` に PR必須、直push禁止、required checks を設定済みであること。

2. CI安定確認
- nightly を含む直近実行が一定期間（例: 3日）で重大失敗なし。

3. 手順整合確認
- `README` と `docs/implementation/*runbook*` の記載が最新実装と一致する。

## 失敗モードと対策
- 設定漏れ: チェックリストで fail とし、再設定後に再確認。
- 手順乖離: ドキュメント更新を必須タスク化。

## テスト観点
- チェックリストが再現可能であること。
- 確認者が変わっても同じ判定に到達できること。

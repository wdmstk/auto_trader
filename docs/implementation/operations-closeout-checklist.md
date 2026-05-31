# 運用完了チェックリスト（通知除外）

- Date: 2026-05-31
- Scope: Branch Protection / CI Stability / Runbook Consistency
- Out of Scope: Notification rollout (Phase 15/16 runtime)

## 1. Branch Protection
- [ ] `main` に branch protection rule がある
  - 証跡:
- [ ] `Require a pull request before merging` が有効
  - 証跡:
- [ ] `Require status checks` が有効
  - 証跡:
- [ ] Required checks に `full`, `smoke`, `validate-gates` が設定済み
  - 証跡:
- [ ] bypass不可（可能なら）設定済み
  - 証跡:

## 2. CI Stability
- [ ] 直近3日で nightly が実行されている
  - 証跡:
- [ ] 直近3日で `smoke` が重大失敗していない
  - 証跡:
- [ ] 直近3日で `full` が重大失敗していない
  - 証跡:
- [ ] failure時に `smoke-report.xml` / `full-report.xml` 回収可能
  - 証跡:

## 3. Runbook Consistency
- [ ] README のCI記載が現行workflowと一致
  - 証跡:
- [ ] `docs/implementation/ci-smoke-triage.md` が現行運用と一致
  - 証跡:
- [ ] `docs/implementation/branch-protection-runbook.md` が現行設定方針と一致
  - 証跡:

## 4. Open Items
- [ ] 未解決項目なし
  - 残件:

## 判定
- [ ] 運用完了（通知除外）
- 判定者:
- 判定日:

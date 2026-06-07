# 運用完了チェックリスト（通知除外）

- Date: 2026-05-31
- Scope: Branch Protection / CI Stability / Runbook Consistency
- Out of Scope: Notification rollout (Phase 15/16 runtime)

## 1. Branch Protection
- [x] `main` に branch protection rule がある
  - 証跡: `gh api repos/wdmstk/auto_trader/branches/main/protection` が 200 で設定取得。
- [x] `Require a pull request before merging` が有効
  - 証跡: `required_pull_request_reviews.required_approving_review_count = 1`。
- [x] `Require status checks` が有効
  - 証跡: `required_status_checks.strict = true`。
- [x] Required checks に `full`, `smoke`, `validate-gates` が設定済み
  - 証跡: `required_status_checks.contexts = [\"full\", \"smoke\", \"validate-gates\"]`。
- [x] bypass不可（可能なら）設定済み
  - 証跡: `enforce_admins.enabled = true`。

## 2. CI Stability
- [x] 直近3日で nightly が実行されている
  - 証跡: `2026-06-03` / `06-04` / `06-05` の schedule run がすべて success。
- [x] 直近3日で `smoke` が重大失敗していない
  - 証跡: `2026-06-05 16:31` の PR run と `2026-06-05 19:27` の nightly run で smoke は success。
- [x] 直近3日で `full` が重大失敗していない
  - 証跡: `2026-06-05 16:31` の PR run で一時的な `Mypy` failure があったが、改善作業後の `2026-06-05 19:27` nightly で full は success。最新状態では問題なし。
- [x] failure時に `smoke-report.xml` / `full-report.xml` 回収可能
  - 証跡: `.github/workflows/ci.yml` で `Upload Smoke Report` / `Upload Full Report` を `if: always()` で設定済み。

## 3. Runbook Consistency
- [x] README のCI記載が現行workflowと一致
  - 証跡: `full/smoke/nightly/artifact` 記載と `.github/workflows/ci.yml` が一致。
- [x] `docs/implementation/ci-smoke-triage.md` が現行運用と一致
  - 証跡: `smoke-report.xml` / `full-report.xml` artifact確認手順を記載済み。
- [x] `docs/implementation/branch-protection-runbook.md` が現行設定方針と一致
  - 証跡: required checks `full/smoke/validate-gates` と設定手順を記載済み。

## 4. Open Items
- [x] 未解決項目なし

## 判定
- [x] 運用完了（通知除外）
- 判定者: Codex
- 判定日: 2026-06-06

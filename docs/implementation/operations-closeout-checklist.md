# 運用完了チェックリスト（通知除外）

- Date: 2026-05-31
- Scope: Branch Protection / CI Stability / Runbook Consistency
- Out of Scope: Notification rollout (Phase 15/16 runtime)

## 1. Branch Protection
- [ ] `main` に branch protection rule がある
  - 証跡: `gh api repos/wdmstk/auto_trader/branches/main/protection` が HTTP 403（プラン制約）でAPI確認不可。Web UI での手動確認が必要。
- [ ] `Require a pull request before merging` が有効
  - 証跡: API確認不可のため未確認（Web UI確認待ち）。
- [ ] `Require status checks` が有効
  - 証跡: API確認不可のため未確認（Web UI確認待ち）。
- [ ] Required checks に `full`, `smoke`, `validate-gates` が設定済み
  - 証跡: `scripts/validate_required_checks.py` 出力 `{\"ok\": true, \"actual\": [\"full\", \"smoke\", \"validate-gates\"], \"missing\": []}`（workflow側定義は確認済み、GitHub保護設定適用は未確認）。
- [ ] bypass不可（可能なら）設定済み
  - 証跡: API確認不可のため未確認（Web UI確認待ち）。

## 2. CI Stability
- [ ] 直近3日で nightly が実行されている
  - 証跡: workflow に `schedule` 設定（`0 18 * * *`）は実装済み。3日分の履歴確認は運用日数不足のため保留。
- [ ] 直近3日で `smoke` が重大失敗していない
  - 証跡: `gh run list --limit 10` で直近 completed run は success。3日連続判定は保留。
- [ ] 直近3日で `full` が重大失敗していない
  - 証跡: `gh run list --limit 10` で直近 completed run は success。3日連続判定は保留。
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
- [ ] 未解決項目なし
  - 残件:
    - GitHub Web UIで branch protection 実設定確認（APIはプラン制約で不可）
    - nightly 実行実績の3日分蓄積待ち

## 判定
- [ ] 運用完了（通知除外）
- 判定者: pending
- 判定日: pending

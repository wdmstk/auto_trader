# ADR-Spec トレーサビリティ（Phase 0-25）

| ADR | 要点 | 反映先Spec |
|---|---|---|
| 0001 | regime/risk/execution/observability優先 | phase0-development-foundation-spec, phase1-data-infrastructure-spec, phase2-feature-engine-spec, phase3-regime-classifier-spec, phase5-range-strategy-spec, phase6-trend-strategy-spec, phase7-ml-pipeline-spec, phase8-backtesting-spec, phase9-stress-testing-spec, phase10-exchange-integration-spec, phase11-position-management-spec, phase12-risk-management-spec, phase13-streamlit-gui-spec, phase14-operations-runbook-spec, phase15-notification-channels-spec, phase16-notify-operations-spec, phase17-end-to-end-smoke-spec, phase18-ci-smoke-automation-spec, phase19-dryrun-orchestrator-spec, phase20-test-profile-separation-spec, phase21-nightly-regression-artifacts-spec, phase22-branch-protection-quality-gates-spec, phase23-ci-policy-drift-guard-spec, phase24-operations-closeout-spec, phase25-gateway-rate-limit-and-error-taxonomy-spec |
| 0002 | isolated・低レバ・DD優先・段階デプロイ | phase0-development-foundation-spec, phase3-regime-classifier-spec, phase10-exchange-integration-spec, phase14-operations-runbook-spec, phase15-notification-channels-spec, phase16-notify-operations-spec, phase17-end-to-end-smoke-spec, phase18-ci-smoke-automation-spec, phase19-dryrun-orchestrator-spec, phase20-test-profile-separation-spec, phase24-operations-closeout-spec, phase25-gateway-rate-limit-and-error-taxonomy-spec |
| 0003 | MLはエントリーフィルタ、TP/SL二値、no shuffle/no leakage | phase2-feature-engine-spec, phase3-regime-classifier-spec, phase4-label-generation-spec, phase5-range-strategy-spec, phase6-trend-strategy-spec, phase7-ml-pipeline-spec, phase8-backtesting-spec, phase17-end-to-end-smoke-spec, phase18-ci-smoke-automation-spec, phase19-dryrun-orchestrator-spec, phase20-test-profile-separation-spec, phase21-nightly-regression-artifacts-spec |

## レビュー観点
1. ADRで定義した禁止事項がSpecで禁止されているか
2. HIGH_VOL停止要件がSpecとテスト戦略で一貫しているか
3. no leakage/no shuffleが実装・検証両方に落ちているか
4. Phase追加時に該当ADRへのトレースが追記されているか

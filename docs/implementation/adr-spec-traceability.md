# ADR-Spec トレーサビリティ（Phase 0-3）

| ADR | 要点 | 反映先Spec |
|---|---|---|
| 0001 | regime/risk/execution/observability優先 | phase0-development-foundation-spec, phase1-data-infrastructure-spec, phase2-feature-engine-spec, phase3-regime-classifier-spec, phase5-range-strategy-spec, phase6-trend-strategy-spec, phase7-ml-pipeline-spec, phase8-backtesting-spec, phase9-stress-testing-spec, phase10-exchange-integration-spec |
| 0002 | isolated・低レバ・DD優先・段階デプロイ | phase0-development-foundation-spec, phase3-regime-classifier-spec, phase10-exchange-integration-spec |
| 0003 | MLはエントリーフィルタ、TP/SL二値、no shuffle/no leakage | phase2-feature-engine-spec, phase3-regime-classifier-spec, phase4-label-generation-spec, phase5-range-strategy-spec, phase6-trend-strategy-spec, phase7-ml-pipeline-spec, phase8-backtesting-spec |

## レビュー観点
1. ADRで定義した禁止事項がSpecで禁止されているか
2. HIGH_VOL停止要件がSpecとテスト戦略で一貫しているか
3. no leakage/no shuffleが実装・検証両方に落ちているか

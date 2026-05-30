# Specレビュー結果（Phase 20）

- Date: 2026-05-31
- Scope: `phase20-test-profile-separation-spec.md`
- Reviewer: Codex

## 結論
Phase 20 は開発速度と回帰品質の両立に有効で、運用可能な実装方針である。

## 固定事項
1. smoke優先
- PRで smoke を即時実行し、早期フィードバックを得る。

2. full維持
- full回帰は継続実行し、網羅性を維持する。

3. 安全ゲート
- smokeに e2e/risk/runtime/orchestrator を必須含有する。

## 残留リスク
- smoke構成の陳腐化により重要ケースが漏れる可能性があるため定期見直しが必要。

## 実装反映ステータス（2026-05-31）
- `pyproject.toml` に `smoke` marker を定義済み。
- `tests/test_e2e_smoke.py`, `tests/test_risk_manager.py`, `tests/test_runtime_control.py`, `tests/test_orchestrator_dryrun.py` に `smoke` マークを付与済み。
- `.github/workflows/ci.yml` で `full` / `smoke` ジョブを分離済み。
- 運用ガイド: `docs/implementation/test-profiles.md` を追加済み。

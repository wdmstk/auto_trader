# CHANGELOG.md

# Crypto FX Trading System - 変更履歴

## 2026-06-23

*   feat: Replace BB mean reversion with horizontal S/R level reversal strategy (#42)
*   fix: wire new range params through pipeline and force feature regeneration (#41)
*   feat: restructure Range strategy with weighted scoring and S/R awareness (#40)
*   fix: handle missing baseline in build_range_quality_report (#39)
*   feat: range strategy tactical improvements (施策 A-E) (#38)
*   feat(gui): add LivePnL OHLCV refresh and performance improvements (#37)
*   refactor: deduplicate code patterns into shared utils module (#36)
*   Add 129 unit tests for least-covered modules (#32)
*   Improve error handling: log swallowed exceptions, narrow catch types, propagate error details (#31)
*   security: fix unsafe pickle deserialization, enforce STARTTLS, validate webhook URLs and GUI file paths (#30)
*   refactor(gui): decompose monolithic app.py into modular components (#35)

## 2026-06-18

*   feat: execution reconciliation, UI/UX improvements, and strategy parameters (a8abbca)
*   refactor: split current work into smaller commits (e8c956c)

## 2026-06-13

*   feat: weekly revalidation drift audit (f094472)
*   feat: weekly autotune route selection pipeline (422722c)

## 2026-06-05

*   feat: notify env templates and candidate trade routes (74c82a8)
*   feat: route-centric trading workflow (0e7181d)
*   feat: runtime control and worker updates (8b98df9)

## 2026-05-30

*   ADR-0001: Regime/Risk/Execution 優先原則 (docs/adr/0001-regime-risk-first-principles.md)
*   ADR-0002: 運用安全基準と段階デプロイ (docs/adr/0002-operational-safety-and-deployment-gates.md)
*   ADR-0003: MLは価格予測器ではなくエントリーフィルタとして使う (docs/adr/0003-ml-as-entry-filter-not-price-predictor.md)
*   Initial project setup and foundation (pyproject.toml, ruff, mypy, pytest, pre-commit, basic config, logging).
*   Docs: Initial ADR, Spec, Implementation Checklist for Phase 0-3.

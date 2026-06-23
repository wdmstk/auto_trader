# AGENTS.md

# Project: Crypto FX Regime-Based Trading System

## Purpose

This repository builds a production-grade cryptocurrency FX trading system. The core purpose is to achieve long-term survivability, controlled drawdown, and operational safety rather than maximizing short-term profits or predicting future prices perfectly. The system aims to participate only in favorable market regimes and meticulously manage risks.

## Architecture Overview

The system is designed as a "market structure recognition + risk management system," not a "price prediction AI." It follows a modular architecture with distinct phases:

1.  **Market Data**: Ingests raw OHLCV data.
2.  **Feature Engine**: Computes technical indicators and other features.
3.  **Regime Classifier**: Identifies market regimes (RANGE, TREND, HIGH_VOL).
4.  **Strategy Engines**: Implements RANGE and TREND specific trading logic, with HIGH_VOL acting as a stop/no-trade condition.
5.  **ML Filter**: Filters low-expectancy setups, acting as an entry gate rather than a price predictor.
6.  **Execution Gating**: Ensures orders are safe to send.
7.  **Position Manager**: Tracks and manages open positions.
8.  **Risk Manager**: Enforces portfolio-level and per-trade risk limits.
9.  **Exchange Execution**: Interfaces with Binance for order submission and real-time updates.
10. **Monitoring / GUI**: Provides real-time observability and human control capabilities via Streamlit.

## AI Responsibilities

The AI's primary responsibilities are:

*   **Market Regime Classification**: Accurately identify RANGE, TREND, and HIGH_VOL market conditions.
*   **Feature Engineering**: Generate robust and non-leaking features for ML models.
*   **Signal Filtering**: Use ML models to filter out low-expectancy trade setups and improve signal quality.
*   **Risk Evaluation**: Assist in evaluating portfolio-level and symbol-specific risks, including correlated exposure.
*   **Operational Monitoring**: Provide insights into system health, performance, and potential issues.
*   **Documentation Assistance**: Generate and maintain consistent project documentation, ensuring clarity and adherence to project rules.

The AI is explicitly **NOT** responsible for:

*   Predicting exact future prices.
*   Introducing high-leverage or high-risk strategies.
*   Over-optimizing for backtest metrics that do not translate to live performance.
*   Bypassing human override or emergency controls.

## Development Workflow

This project adheres to a **Documentation-First Workflow**.

1.  **Spec/ADR Update**: Any behavioral change requires updating the relevant `docs/specs/` and `docs/adr/` before code modifications.
2.  **Review/Checklist**: Create or update matching review documents in `docs/implementation/` and phase implementation checklists.
3.  **Code Implementation**: Implement changes strictly following the updated documentation.
4.  **Testing & Verification**: Run comprehensive tests (unit, integration, simulation, stress, exchange) and record results.
5.  **Deployment**: Follow the strict `DryRun -> Testnet -> Production` phased deployment process with mandatory gate checks.

## Coding Philosophy

*   **Safety First**: Prioritize system survivability and risk control over speculative profits.
*   **Explainability**: Every entry, exit, and significant system decision must be traceable and explainable through logs and metrics.
*   **Modularity**: Codebase should be modular, with clear separation of concerns (e.g., data, features, regime, strategy, risk, execution).
*   **Type Safety**: Strict type hinting (`mypy`) is enforced to ensure code correctness and maintainability.
*   **Immutability**: Favor immutable data structures and functional patterns where appropriate to reduce side effects.
*   **Robustness**: Design for resilience against external failures (e.g., API disconnects, partial fills, stale data).

## Review Process

All significant changes must undergo a thorough review process focusing on:

*   Adherence to `base_policy.md`, `PROJECT_RULES.md`, and `AGENT.md`.
*   Completeness and consistency of documentation (ADR, Specs, Checklists).
*   Risk implications and mitigation strategies.
*   Test coverage and validation results.
*   Code quality, maintainability, and performance.
*   Observability of new features or changes.

## Testing Requirements

Comprehensive testing is mandatory across all layers:

*   **Unit Tests**: For individual functions and small modules (`src/auto_trader/*`).
*   **Integration Tests**: For interactions between components (e.g., exchange integration, GUI interaction, strategy pipelines).
*   **Simulation Tests**: To validate behavior under various market conditions (e.g., flash crash, liquidity vacuum).
*   **Stress Tests**: To evaluate system robustness under extreme loads or adverse events (e.g., 2x volatility, API timeout).
*   **Walk Forward Validation**: For ML models and strategy performance evaluation to prevent overfitting.
*   **CI/CD Integration**: All tests are integrated into GitHub Actions, with `smoke` (fast, high-signal) and `full` (comprehensive regression) suites, including nightly runs.

## Project Evolution

The agent should always understand that this project evolves iteratively with a strong emphasis on risk management and operational stability. New features or strategies should be introduced incrementally, thoroughly documented, and rigorously tested through defined deployment gates. The focus remains on building a robust, long-term viable trading system that can adapt to changing market conditions while minimizing exposure to catastrophic risks.

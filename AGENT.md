# AGENT.md

# Project: Crypto FX Regime-Based Trading System

## Purpose

This repository builds a production-grade cryptocurrency FX trading system.

The goal is NOT:

* maximizing backtest metrics
* predicting future prices perfectly
* over-optimizing for PF

The goal IS:

* long-term survivability
* controlled drawdown
* regime adaptation
* operational safety
* explainability
* stable execution
* risk-first architecture

---

# Core Philosophy

Priority order:

1. Regime detection
2. Risk management
3. Execution safety
4. Observability
5. Strategy quality
6. Prediction quality

---

# Documentation-First Workflow

Any behavior-affecting change must follow this order:

1. Update the relevant spec in `docs/specs/`.
2. Write or update the matching spec review in `docs/implementation/`.
3. Update the phase implementation checklist in `docs/implementation/`.
4. Implement the code change.
5. Run the relevant tests and record the result back into the review/checklist.

Do not ship behavioral code changes without a matching spec/review/checklist trail.
If docs and code diverge, reconcile the docs first and then bring the code back in line.
This also applies to route-selection, worker execution, report schema, and migration work.
When a change affects persisted data or runtime inputs, document the target schema and
backward-compatibility rule before editing code.

---

# System Philosophy

This is NOT a:

* "price prediction AI"

This IS a:

* "market structure recognition + risk management system"

---

# Mandatory Principles

## Regime First

Always classify market structure first.

Supported regimes:

* RANGE
* TREND
* HIGH_VOL

No strategy should run without regime awareness.

---

## Risk First

Protect capital before seeking profit.

Mandatory:

* isolated margin only
* low leverage (1-3x)
* max risk per trade
* max portfolio exposure
* DD limits

---

## Execution Safety

Never assume orders succeeded.

All execution logic must support:

* retry
* reconnect
* timeout handling
* duplicate prevention
* stale signal prevention

---

## Observability

Every important action must be explainable.

Log:

* features
* regime
* ML score
* entry reason
* exit reason
* SL movement
* add position reason
* execution errors

---

# Forbidden Practices

## Absolutely Forbidden

* future leakage
* shuffled timeseries training
* CROSS margin
* martingale
* unrestricted averaging down
* high leverage
* overfit feature spam
* metric cherry-picking
* ignoring DD

---

# ML Philosophy

ML is NOT used to predict exact future prices.

ML is used to:

* filter low expectancy setups
* avoid bad conditions
* detect regime-dependent edge

---

# Labeling Rules

Use binary classification only.

Example:

* TP = +4%
* SL = -2%

Label:

* 1 = TP hit first
* 0 = SL hit first

Do NOT use raw future_return regression.

---

# Strategy Separation

RANGE and TREND are fundamentally different systems.

Never force one logic into both.

---

# RANGE Philosophy

Goal:

* capture mean reversion

Features:

* RSI rebound
* BB mean reversion
* wick rejection
* support/resistance

---

# TREND Philosophy

Goal:

* capture continuation

Features:

* breakout persistence
* momentum persistence
* trend efficiency
* pullback shallowness

---

# HIGH VOL Philosophy

Default action:

NO TRADE

---

# Walk Forward Rules

Mandatory:

* no shuffle
* no leakage
* chronological split only

Recommended:

* 6m train
* 2m validation
* 2m test

---

# Acceptance Criteria

Minimum production standards:

* PF > 1.2
* positive expectancy
* stable walkforward
* acceptable DD
* no catastrophic month

---

# Production Safety

Production deployment requires:

1. DryRun success
2. Testnet stability
3. No critical execution bugs
4. Stable monitoring
5. Human validation

---

# GUI Philosophy

The GUI is NOT decorative.

The GUI exists to:

* prevent operational mistakes
* detect abnormal conditions
* allow emergency intervention
* visualize market structure

---

# Emergency Controls

Always visible:

* START
* STOP
* EMERGENCY STOP
* EMERGENCY CANCEL
* CLOSE ALL

---

# Multi-Symbol Rules

Portfolio risk matters more than single-symbol risk.

Must manage:

* correlation
* clustered exposure
* concurrent regime risk

---

# Parallelization Rules

Optimization and backtests must support:

* multiprocessing
* async execution
* caching
* incremental computation

---

# Code Quality Rules

Mandatory:

* typed code
* pydantic configs
* pytest coverage
* modular architecture
* feature isolation
* exchange abstraction

---

# Testing Philosophy

Every bug in production is expensive.

Test aggressively.

Required:

* unit tests
* integration tests
* simulation tests
* stress tests
* exchange tests
* websocket tests

---

# Operational Philosophy

A boring stable system is better than:

* flashy equity curves
* unstable PF spikes
* overfit models

Survival first.

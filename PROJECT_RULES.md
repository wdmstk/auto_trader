# PROJECT_RULES.md

# Development Rules

---

# Rule 1 - Safety First

Never prioritize profit over survivability.

---

# Rule 2 - DD Matters More Than PF

A high PF with catastrophic DD is failure.

---

# Rule 3 - Regime Matters

No feature is universally valid.

Always consider:

* RANGE
* TREND
* HIGH_VOL

---

# Rule 4 - Avoid Overfitting

Do not:

* add random indicators
* optimize endlessly
* tune for one market phase

---

# Rule 5 - Explainability Required

Every entry should be explainable.

---

# Rule 6 - Production != Backtest

Backtests are optimistic.

Always assume:

* slippage worse
* execution delayed
* spreads wider

---

# Rule 7 - No Hidden Risk

Always visualize:

* exposure
* leverage
* correlation
* DD

---

# Rule 8 - Human Override Required

Human emergency intervention must always be possible.

---

# Rule 9 - Incremental Deployment

Deployment order:

1. DryRun
2. Testnet
3. Production

Never skip stages.

---

# Rule 10 - Monitoring Is Mandatory

If it cannot be monitored,
it should not run.

---

# Rule 11 - Portfolio Risk > Symbol Risk

Correlated exposure kills accounts.

---

# Rule 12 - Stability Wins

Prefer:

* stable PF
* smooth equity
* lower DD

over:

* flashy returns
* unstable spikes

---

# Rule 13 - Logging Is Critical

Every important action must leave logs.

---

# Rule 14 - Parallelism Must Be Safe

Parallel optimization must not:

* corrupt data
* mix timestamps
* leak future information

---

# Rule 15 - Never Trust The Exchange

Always handle:

* disconnects
* stale data
* rejected orders
* partial fills

---

# Final Principle

A system that survives for years
is superior to a system
that looks amazing for one month.

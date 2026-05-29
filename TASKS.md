# TASKS.md

# Crypto FX Trading System - Master Tasks

---

# PHASE 0 - Repository Foundation

* [ ] Initialize repository structure
* [ ] Setup pyproject.toml
* [ ] Setup linting
* [ ] Setup formatting
* [ ] Setup typing
* [ ] Setup pytest
* [ ] Setup pre-commit hooks
* [ ] Setup environment config
* [ ] Setup logging system

---

# PHASE 1 - Data Infrastructure

## Historical Data

* [ ] Binance historical downloader
* [ ] OHLCV validation
* [ ] Missing candle detection
* [ ] Duplicate candle detection
* [ ] Timezone normalization

## Storage

* [ ] parquet storage
* [ ] incremental updates
* [ ] caching layer

---

# PHASE 2 - Feature Engine

## Common Features

* [ ] RSI
* [ ] ATR
* [ ] BB Width
* [ ] Volume ratio
* [ ] MA distance
* [ ] Trend efficiency

## RANGE Features

* [ ] Wick ratio
* [ ] Mean reversion distance
* [ ] Reversal candle detection

## TREND Features

* [ ] Momentum persistence
* [ ] Breakout persistence
* [ ] Pullback shallowness
* [ ] Higher high persistence

---

# PHASE 3 - Regime Classifier

* [ ] RANGE detection
* [ ] TREND detection
* [ ] HIGH VOL detection
* [ ] Regime transition logic
* [ ] Regime visualization

---

# PHASE 4 - Label Generation

* [ ] TP/SL binary labels
* [ ] Leakage validation
* [ ] Timestamp integrity checks

---

# PHASE 5 - RANGE Strategy

* [ ] Entry conditions
* [ ] Exit conditions
* [ ] Risk controls
* [ ] Position sizing
* [ ] Backtest validation

---

# PHASE 6 - TREND Strategy

* [ ] Breakout continuation
* [ ] Trend continuation
* [ ] Pyramid logic
* [ ] Trailing logic
* [ ] Exit structure logic

---

# PHASE 7 - ML Pipeline

* [ ] Dataset builder
* [ ] Feature selection
* [ ] LightGBM training
* [ ] Calibration checks
* [ ] Threshold optimization
* [ ] WalkForward pipeline

---

# PHASE 8 - Backtesting

* [ ] Fee modeling
* [ ] Slippage modeling
* [ ] Spread modeling
* [ ] Delayed execution modeling
* [ ] Portfolio simulation

---

# PHASE 9 - Stress Testing

* [ ] 2x volatility
* [ ] Flash crash simulation
* [ ] Liquidity vacuum simulation
* [ ] Spread widening simulation
* [ ] API timeout simulation

---

# PHASE 10 - Exchange Integration

* [ ] CCXT wrapper
* [ ] Binance websocket
* [ ] Retry logic
* [ ] Reconnect logic
* [ ] Duplicate order prevention

---

# PHASE 11 - Position Management

* [ ] Average entry tracking
* [ ] Pyramid tracking
* [ ] Exposure management
* [ ] Portfolio correlation management

---

# PHASE 12 - Risk Management

* [ ] Max DD control
* [ ] Max symbol exposure
* [ ] Max portfolio exposure
* [ ] Correlation risk control
* [ ] Emergency shutdown

---

# PHASE 13 - Streamlit GUI

## Dashboard

* [ ] PnL panel
* [ ] Regime panel
* [ ] Exposure panel
* [ ] Whale activity panel

## Controls

* [ ] START
* [ ] STOP
* [ ] EMERGENCY STOP
* [ ] EMERGENCY CANCEL
* [ ] CLOSE ALL

## Visualization

* [ ] Candlestick chart
* [ ] Regime overlay
* [ ] Entry/Exit overlay
* [ ] ML score overlay
* [ ] WalkForward charts

---

# PHASE 14 - Multi Symbol

* [ ] Symbol management
* [ ] Symbol-specific configs
* [ ] Portfolio exposure map
* [ ] Correlation matrix

---

# PHASE 15 - Parallelization

* [ ] multiprocessing
* [ ] async websocket
* [ ] parallel backtests
* [ ] parallel walkforward
* [ ] optuna parallel optimization

---

# PHASE 16 - MLOps

* [ ] Model versioning
* [ ] Feature versioning
* [ ] Drift detection
* [ ] Retraining pipeline
* [ ] Rollback support

---

# PHASE 17 - Testing

## Unit Tests

* [ ] Feature tests
* [ ] Label tests
* [ ] Risk tests
* [ ] Execution tests

## Integration Tests

* [ ] Exchange integration
* [ ] GUI integration
* [ ] Strategy integration

## Simulation Tests

* [ ] Flash crash
* [ ] Execution delay
* [ ] Websocket disconnect

---

# PHASE 18 - Deployment

## DryRun

* [ ] Validate execution flow
* [ ] Validate GUI
* [ ] Validate monitoring

## Testnet

* [ ] Validate order flow
* [ ] Validate recovery
* [ ] Validate emergency controls

## Production

* [ ] Final readiness checklist
* [ ] Monitoring verification
* [ ] Rollback verification

---

# PHASE 19 - Monitoring

* [ ] PF drift
* [ ] DD drift
* [ ] Feature drift
* [ ] Regime drift
* [ ] Execution latency
* [ ] API health

---

# PHASE 20 - Documentation

* [ ] Architecture docs
* [ ] Feature docs
* [ ] Risk docs
* [ ] GUI docs
* [ ] Deployment docs
* [ ] Operational playbook

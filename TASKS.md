# TASKS.md

# Crypto FX Trading System - Master Tasks

## Current Sprint

- [ ] Binance OHLCV取得・正規化・Parquet保存 (Phase 1)
- [ ] 特徴量エンジン (Phase 2)
- [ ] Regime分類器（`HIGH_VOL = NO TRADE` 強制）(Phase 3)

## Backlog

### PHASE 0 - Repository Foundation

*   [ ] Initialize repository structure
*   [ ] Setup pyproject.toml
*   [ ] Setup linting
*   [ ] Setup formatting
*   [ ] Setup typing
*   [ ] Setup pytest
*   [ ] Setup pre-commit hooks
*   [ ] Setup environment config
*   [ ] Setup logging system

### PHASE 1 - Data Infrastructure

*   [ ] OHLCV validation
*   [ ] Missing candle detection
*   [ ] Duplicate candle detection
*   [ ] Timezone normalization
*   [ ] parquet storage
*   [ ] incremental updates
*   [ ] caching layer

### PHASE 2 - Feature Engine

*   [ ] RSI
*   [ ] ATR
*   [ ] BB Width
*   [ ] Volume ratio
*   [ ] MA distance
*   [ ] Trend efficiency
*   [ ] Wick ratio
*   [ ] Mean reversion distance
*   [ ] Reversal candle detection
*   [ ] Momentum persistence
*   [ ] Breakout persistence
*   [ ] Pullback shallowness
*   [ ] Higher high persistence

### PHASE 3 - Regime Classifier

*   [ ] RANGE detection
*   [ ] TREND detection
*   [ ] Regime transition logic
*   [ ] Regime visualization

### PHASE 4 - Label Generation

*   [ ] TP/SL binary labels
*   [ ] Leakage validation
*   [ ] Timestamp integrity checks

### PHASE 5 - RANGE Strategy

*   [ ] Entry conditions
*   [ ] Exit conditions
*   [ ] Risk controls
*   [ ] Position sizing
*   [ ] Backtest validation

### PHASE 6 - TREND Strategy

*   [ ] Breakout continuation
*   [ ] Trend continuation
*   [ ] Pyramid logic
*   [ ] Trailing logic
*   [ ] Exit structure logic

### PHASE 7 - ML Pipeline

*   [ ] Dataset builder
*   [ ] Feature selection
*   [ ] LightGBM training
*   [ ] Calibration checks
*   [ ] Threshold optimization
*   [ ] WalkForward pipeline

### PHASE 8 - Backtesting

*   [ ] Fee modeling
*   [ ] Slippage modeling
*   [ ] Spread modeling
*   [ ] Delayed execution modeling
*   [ ] Portfolio simulation

### PHASE 9 - Stress Testing

*   [ ] 2x volatility
*   [ ] Flash crash simulation
*   [ ] Liquidity vacuum simulation
*   [ ] Spread widening simulation
*   [ ] API timeout simulation

### PHASE 10 - Exchange Integration

*   [ ] CCXT wrapper
*   [ ] Binance websocket
*   [ ] Retry logic
*   [ ] Reconnect logic
*   [ ] Duplicate order prevention

### PHASE 11 - Position Management

*   [ ] Average entry tracking
*   [ ] Pyramid tracking
*   [ ] Exposure management
*   [ ] Portfolio correlation management

### PHASE 12 - Risk Management

*   [ ] Max DD control
*   [ ] Max symbol exposure
*   [ ] Max portfolio exposure
*   [ ] Correlation risk control
*   [ ] Emergency shutdown

### PHASE 13 - Streamlit GUI

*   [ ] PnL panel
*   [ ] Regime panel
*   [ ] Exposure panel
*   [ ] Whale activity panel
*   [ ] START
*   [ ] STOP
*   [ ] EMERGENCY STOP
*   [ ] EMERGENCY CANCEL
*   [ ] CLOSE ALL
*   [ ] Candlestick chart
*   [ ] Regime overlay
*   [ ] Entry/Exit overlay
*   [ ] ML score overlay
*   [ ] WalkForward charts

### PHASE 14 - Multi Symbol

*   [ ] Symbol management
*   [ ] Symbol-specific configs
*   [ ] Portfolio exposure map
*   [ ] Correlation matrix

### PHASE 15 - Parallelization

*   [ ] multiprocessing
*   [ ] async websocket
*   [ ] parallel backtests
*   [ ] parallel walkforward
*   [ ] optuna parallel optimization

### PHASE 16 - MLOps

*   [ ] Model versioning
*   [ ] Feature versioning
*   [ ] Drift detection
*   [ ] Retraining pipeline
*   [ ] Rollback support

### PHASE 17 - Testing

*   [ ] Feature tests
*   [ ] Label tests
*   [ ] Risk tests
*   [ ] Execution tests
*   [ ] Exchange integration
*   [ ] GUI integration
*   [ ] Strategy integration
*   [ ] Flash crash
*   [ ] Execution delay
*   [ ] Websocket disconnect

### PHASE 18 - Deployment

*   [ ] Validate execution flow
*   [ ] Validate GUI
*   [ ] Validate monitoring
*   [ ] Validate order flow
*   [ ] Validate recovery
*   [ ] Validate emergency controls
*   [ ] Final readiness checklist
*   [ ] Monitoring verification
*   [ ] Rollback verification

### PHASE 19 - Monitoring

*   [ ] PF drift
*   [ ] DD drift
*   [ ] Feature drift
*   [ ] Regime drift
*   [ ] Execution latency
*   [ ] API health

### PHASE 20 - Documentation

*   [ ] Architecture docs
*   [ ] Feature docs
*   [ ] Risk docs
*   [ ] GUI docs
*   [ ] Deployment docs
*   [ ] Operational playbook

## Technical Debt

(現在のプロジェクトで特定された技術的負債をここに追加します。例: レガシーコードの置き換え、不必要な複雑さの解消など)

## Future Ideas

(将来的に検討したいアイデアをここに追加します。例: 新しい戦略の追加、異なる取引所との連携、追加のモニタリング指標など)

## Priority

各タスクには相対的な優先度を割り当てます（例: High, Medium, Low）。

## Estimated Complexity

各タスクには相対的な複雑さを割り当てます（例: Small, Medium, Large）。

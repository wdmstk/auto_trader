# 暗号資産FX 自動売買システム 完全再構築 要件まとめ

# ■ システム目的

本システムの目的は：

* 長期生存
* DD（最大ドローダウン）制御
* 危険相場回避
* 有利相場のみ参加
* 実運用耐性
* 誤発注防止
* 可観測性（observability）
* GUIによる安全運用

であり、

「未来価格を完璧に当てるAI」

ではなく、

# 「市場構造認識 + リスク管理システム」

として設計する。

---

# ■ 最重要思想

* regime first
* risk first
* execution safety first
* observability first
* UX/UI first
* prediction last

---

# ■ 市場構造（Regime）

## 1. RANGE

特徴：

* 横ばい
* 低ボラ
* mean reversion
* fake breakout多い

戦略：

* RSI反発
* BB反発
* support/resistance rebound

---

## 2. TREND

特徴：

* breakout continuation
* momentum persistence
* shallow pullback
* BB expansion
* ADX高

戦略：

* breakout continuation
* momentum continuation
* pyramid
* trailing

---

## 3. HIGH VOL

特徴：

* ATR extreme
* liquidation cascade
* abnormal volatility
* whale activity

戦略：

* NO TRADE

---

# ■ システム構成

```text id="56i1nf"
market data
↓
feature engine
↓
regime classifier
↓
strategy engines
    ├ RANGE engine
    ├ TREND engine
    └ HIGH VOL stop
↓
ML filter
↓
execution gating
↓
position manager
↓
risk manager
↓
exchange execution
↓
monitoring / GUI
```

---

# ■ ML思想

MLの役割：

# 「期待値がある場面だけ通す」

方向予測AIではない。

---

# ■ ラベル設計

binary classificationを採用。

## TP/SL先着方式

例：

* TP +4%
* SL -2%

先着で：

* 1 = TP first
* 0 = SL first

---

# ■ 禁止事項

* future_return回帰
* top-k選別
* leakage
* shuffle
* high leverage
* CROSS
* ナンピン
* high vol追従
* regime無視

---

# ■ RANGE Engine

## Feature

* RSI rebound
* BB mean reversion
* wick ratio
* support distance
* reversal candle

## Entry

* RSI40〜50反発
* support touch
* lower wick

## Exit

* resistance
* BB mean
* momentum loss

---

# ■ TREND Engine

## Feature

* momentum persistence
* breakout persistence
* trend efficiency
* pullback shallowness
* volume continuation
* higher high persistence

## Entry

* breakout continuation
* retest success
* shallow pullback

## Exit

* structure break
* lower high
* exhaustion
* ATR spike

---

# ■ Pyramid / Scaling

## RANGE

* 分割entryのみ

## TREND

* pyramid許可

条件：

* 含み益中のみ
* add逓減
* high vol禁止
* max_add_count制限

---

# ■ リスク管理

* isolated only
* leverage 1〜3x
* 1 trade risk <= 1%
* portfolio risk管理
* correlated exposure制御
* DD limit
* exposure limit

---

# ■ マルチ銘柄対応

対応例：

* BTC
* ETH
* SOL
* XRP
* BNB

---

# ■ 銘柄別管理

銘柄ごとに：

* regime
* threshold
* model
* DD
* exposure
* volatility
* ML score

を独立管理。

---

# ■ モデル構成

## 1. Global Model

全銘柄共通

## 2. Symbol-specific Model

銘柄別最適化

## 3. Hybrid Model

共通 + 銘柄補正

---

# ■ ポートフォリオ管理

管理：

* rolling correlation
* exposure clustering
* portfolio DD
* concurrent trades
* correlated exposure

---

# ■ Walk Forward

推奨：

```text id="h1b1qg"
6m train
2m validation
2m test
```

---

# ■ バックテスト

必須：

* fee
* slippage
* spread
* execution delay

---

# ■ Stress Test

必須：

* 2x volatility
* flash crash
* low liquidity
* spread widening
* API timeout

---

# ■ Streamlit GUI

## Dashboard表示

* current regime
* positions
* pnl
* DD
* exposure
* ML confidence
* whale activity
* volatility
* API status

---

# ■ GUI操作

必須：

* START
* STOP
* EMERGENCY STOP
* EMERGENCY CANCEL
* CLOSE ALL

---

# ■ Chart GUI

ろうそく足へ：

* regime
* entry
* exit
* add point
* SL/TP
* ML score
* volatility state

を重ね表示。

---

# ■ WalkForward GUI

表示：

* equity curve
* PF
* Expectancy
* DD
* monthly pnl
* regime別成績

---

# ■ 運用モード

## 1. DryRun

仮想注文のみ

## 2. Testnet

Binance Testnet

## 3. Production

実発注

---

# ■ Production移行条件

以下必須：

* stable WalkForward
* stable Testnet
* acceptable DD
* catastrophic monthなし

---

# ■ Binance統合

* websocket優先
* reconnect
* retry
* rate limit対応

---

# ■ 並列処理

目的：

* optimization高速化
* WalkForward短TAT
* retraining高速化

---

# ■ 並列対象

* symbol別backtest
* feature generation
* hyperparameter optimization
* retraining
* stress test

---

# ■ 推奨技術

* multiprocessing
* asyncio
* concurrent.futures
* joblib
* Ray
* Dask

---

# ■ 高速化

* parquet
* feather
* feature cache
* vectorized operation
* incremental update

---

# ■ Monitoring

監視：

* PF drift
* DD drift
* feature drift
* latency
* websocket disconnect
* API error

---

# ■ Alert

通知：

* Discord
* Telegram
* GUI alert

---

# ■ MLOps

* model versioning
* rollback
* feature versioning
* retraining pipeline
* drift detection

---

# ■ テスト設計

## Unit Test

* feature
* label
* regime
* SL/TP
* execution

## Integration Test

* exchange
* websocket
* GUI

## Simulation Test

* flash crash
* liquidation cascade
* fake breakout

## DryRun Test

仮想運用

## Testnet Test

本番相当検証

---

# ■ Acceptance Criteria

最低条件：

* PF > 1.2
* positive expectancy
* stable WalkForward
* controlled DD
* no catastrophic month

---

# ■ 最重要

目的は：

# 「バックテスト映え」

ではない。

目的は：

# 「本番で壊れにくく、

長期運用でき、
人間が安全に監視できる、
実運用耐性の高いシステム」

を構築すること。

# ■ 追加要件：マルチ銘柄運用 + 並列最適化

========================================

# ■ マルチ銘柄運用

========================================

本システムは：

単一銘柄専用

ではなく、

---

## 複数銘柄同時運用

を前提として設計すること。

========================================

# ■ 対応対象

========================================

例：

* BTCUSDT
* ETHUSDT
* SOLUSDT
* XRPUSDT
* BNBUSDT

など。

========================================

# ■ 最重要

========================================

銘柄ごとに：

* ボラ
* liquidity
* trend persistence
* spread
* behavior

が異なる。

そのため：

---

## symbol-specific optimization

を必須とする。

========================================

# ■ 銘柄ごとに管理するもの

========================================

* regime
* feature stats
* threshold
* model
* exposure
* DD
* volatility
* execution state
* ML score
* walkforward metrics

========================================

# ■ model architecture

========================================

以下を比較可能にすること：

---

1. Global model

---

全銘柄共通モデル

---

2. Symbol-specific model

---

銘柄別モデル

---

3. Hybrid model

---

共通feature + 銘柄別補正

========================================

# ■ 銘柄相関管理

========================================

超重要。

========================================

# ■ 必須

========================================

同方向高相関exposure制御。

例：

BTC long
+
ETH long
+
SOL long

で実質risk集中しないよう制御。

========================================

# ■ correlation risk

========================================

以下を実装：

* rolling correlation
* exposure clustering
* portfolio DD
* sector concentration

========================================

# ■ portfolio risk manager

========================================

単銘柄ではなく：

---

## portfolio basis

でrisk管理。

========================================

# ■ 制御

========================================

* max portfolio DD
* max correlated exposure
* max symbol exposure
* max concurrent trades
* regime weighted exposure

========================================

# ■ GUI追加

========================================

Dashboardへ：

* symbol list
* symbol regime
* symbol pnl
* symbol DD
* symbol ML confidence
* symbol exposure

表示。

========================================

# ■ Multi-symbol visualization

========================================

以下をGUI表示：

* symbol heatmap
* regime map
* pnl ranking
* DD ranking
* correlation matrix
* active trades map

========================================

# ■ WalkForward

========================================

銘柄別に：

* PF
* Expectancy
* DD
* stability

を比較可能。

========================================

# ■ 並列処理

========================================

超重要。

========================================

# ■ 目的

========================================

* optimization高速化
* WalkForward短TAT
* retraining短縮
* backtest高速化

========================================

# ■ 必須

========================================

CPU並列処理対応。

========================================

# ■ 推奨

========================================

* multiprocessing
* concurrent.futures
* joblib
* Ray
* Dask

など比較検討。

========================================

# ■ 並列対象

========================================

* symbol別backtest
* WalkForward
* feature generation
* retraining
* hyperparameter optimization
* stress test

========================================

# ■ Hyperparameter Optimization

========================================

optuna並列化対応。

========================================

# ■ GPU

========================================

将来的GPU利用も考慮。

========================================

# ■ async architecture

========================================

リアルタイム系は：

* asyncio
* websocket async
* non-blocking design

を採用。

========================================

# ■ Streamlit性能

========================================

重要：

* caching
* incremental update
* lazy rendering
* async refresh

を導入。

========================================

# ■ 高速化設計

========================================

以下を実装：

* parquet利用
* feather利用
* feature cache
* incremental feature update
* rolling precompute
* vectorized operation

========================================

# ■ Data Pipeline

========================================

銘柄ごとに：

* independent pipeline
* isolated failure handling

を採用。

========================================

# ■ failure isolation

========================================

重要。

1銘柄異常で：

全体停止しない。

========================================

# ■ Scheduler

========================================

並列job scheduler導入。

========================================

# ■ Monitoring

========================================

監視：

* CPU usage
* memory usage
* queue backlog
* retraining latency
* websocket latency

========================================

# ■ 実装してほしい内容（追加）

========================================

以下を追加出力：

1. multi-symbol architecture
2. portfolio risk manager
3. symbol-specific model設計
4. hybrid model設計
5. correlation management
6. concurrent execution設計
7. multiprocessing設計
8. async websocket設計
9. parallel WalkForward
10. distributed optimization
11. caching戦略
12. Streamlit performance optimization
13. scheduler設計
14. failure isolation設計
15. resource monitoring
16. scalable directory構成
17. sample concurrent code
18. benchmark方法
19. TAT改善方法
20. 実運用注意点

========================================

# ■ 最重要

========================================

目的は：

「大量銘柄を無理に回すこと」

ではない。

目的は：

「複数銘柄を、
安全に、
高速に、
監視可能な状態で、
安定運用すること」

である。

また：

* observability
* scalability
* maintainability
* operational safety

を最優先してください。

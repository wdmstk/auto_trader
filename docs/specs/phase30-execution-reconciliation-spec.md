# Phase 30 Spec: Execution Reconciliation Service

- Version: 1.0
- Date: 2026-06-18
- Related ADR: 0001, 0002
- Related Phase: 25 (gateway integration)

## 目的
注文のACKを即時約定として扱う現在の実装を改善し、実際の約定レポートに基づいて正確にポジションを更新する実行整合性サービスを導入する。これにより、ローカルポジションと取引所ポジションの不一致を排除し、リスクエクスポージャーとPnL計算の正確性を確保する。

## 背景と問題点

### 現状の課題
- Binanceの`accepted:NEW`は注文受付確認であり、約定完了ではない
- 現在の実装はACKを即時FillEventとして処理し、ポジションを更新している
- 部分約定、重複イベント、順序逆転が考慮されていない
- 再起動後の整合性チェックが不十分

### 影響範囲
- ローカルポジション vs 取引所ポジションの不一致
- リスクエクスポージャー計算の誤差
- PnL追跡の信頼性低下
- 緊急時の正確なポジション把握が困難

## 入力（I/O契約）

### リコンサイラー入力
- 取引所WebSocket/RESTからの実行イベント（execution reports）
- 注文発行時のclient_order_id
- 現在のローカルポジション状態
- 取引所ポジション状態（定期同期）

### イベントタイプ
- `ORDER_ACK`: 注文受付確認
- `ORDER_PARTIAL_FILLED`: 部分約定
- `ORDER_FILLED`: 完全約定
- `ORDER_CANCELLED`: 注文キャンセル
- `ORDER_EXPIRED`: 有効期限切れ
- `ORDER_REJECTED`: 注文拒否

## 出力（I/O契約）

### FillEvent出力
- 約定済み数量のみを含むFillEvent
- 累積約定価格（加重平均）
- 実際の約定タイムスタンプ
- 取引所order_idとの紐付け

### 整合性メトリクス
- 保留中注文数
- 未整合注文数
- 平均約定レイテンシー
- 最終整合性チェック時刻
- ポジション不一致フラグ

### 状態管理
- 保留中注文状態（pending_orders）
- 注文ライフサイクル履歴
- 整合性チェック結果

## 前提条件
- Phase 25のgateway永続化機能が実装済み
- 取引所WebSocketからの実行レポート受信機能が利用可能
- 既存のPositionManagerとFillEventスキーマが存在

## 仕様

### 1. 注文ライフサイクル状態マシン

#### 状態定義
```python
enum OrderState:
    PENDING_SUBMIT    # 発行前
    PENDING_ACK       # ACK待ち
    ACKED             # 受付確認済み
    PARTIALLY_FILLED  # 部分約定中
    FILLED            # 完全約定
    CANCELLED         # キャンセル済み
    EXPIRED           # 有効期限切れ
    REJECTED          # 拒否済み
    UNKNOWN           # 不明な状態
```

#### 状態遷移ルール
- `PENDING_SUBMIT` → `PENDING_ACK`: 注文発行時
- `PENDING_ACK` → `ACKED`: ACK受領時
- `PENDING_ACK` → `REJECTED`: 拒否受領時
- `ACKED` → `PARTIALLY_FILLED`: 部分約定時
- `PARTIALLY_FILLED` → `FILLED`: 完全約定時
- `ACKED/PARTIALLY_FILLED` → `CANCELLED`: キャンセル時
- `PENDING_ACK/ACKED` → `EXPIRED`: 有効期限切れ時

### 2. Fill Tracker

#### 機能
- 注文ごとの累積約定数量を追跡
- 約定価格の加重平均を計算
- 最終約定タイムスタンプを記録

#### 計算ロジック
```python
cumulative_qty += fill_qty
weighted_price_sum += fill_qty * fill_price
avg_fill_price = weighted_price_sum / cumulative_qty
```

#### 重複排除
- 同一execution reportの重複処理を防止
- `trade_id`または一意のイベントIDで重複検出
- 処理済みイベントのIDキャッシュ

### 3. Execution Reconciler

#### 中核機能
- 実行イベントを注文ライフサイクルにマッピング
- 約定時のみFillEventを生成
- ポジション更新タイミングを制御

#### イベント処理フロー
1. 実行イベント受領
2. client_order_idで保留中注文を検索
3. 注文状態を更新
4. 約定イベントの場合のみFillEventを生成
5. FillEventをPositionManagerに渡す

#### 順序逆転対応
- イベントタイムスタンプで順序保証
- 遅延イベントの適切な処理
- 状態整合性の維持

### 4. 定期整合性チェック

#### チェック項目
- 保留中注文 vs 取引所オープン注文
- ローカルポジション vs 取引所ポジション
- 未処理実行レポートの有無

#### 不一致検出時の対応
- アラート発報
- GUIでの視覚的表示
- 手動介入フラグの設定
- 自動修正オプション（設定可能）

### 5. 再起動復旧

#### 復旧手順
1. 保留中注文状態を永続化から復元
2. 取引所から現在のオープン注文を取得
3. 状態を照合し不一致を検出
4. 必要に応じて手動修正プロンプト

#### 復旧安全性
- 不明確な状態では安全側にフォールバック
- 緊急停止オプションの提供
- 復旧ログの詳細記録

## データ構造

### OrderLifecycle
```python
@dataclass
class OrderLifecycle:
    client_order_id: str
    exchange_order_id: str | None
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: float | None
    state: OrderState
    cumulative_filled_qty: float = 0.0
    avg_fill_price: float = 0.0
    created_at: datetime
    updated_at: datetime
    filled_at: datetime | None = None
    processed_events: set[str] = field(default_factory=set)
```

### ReconciliationState
```python
@dataclass
class ReconciliationState:
    pending_orders: dict[str, OrderLifecycle]
    last_check_at: datetime
    mismatch_count: int = 0
    last_mismatch_details: dict[str, Any] = field(default_factory=dict)
```

## 設定項目

### ReconciliationConfig
```python
@dataclass
class ReconciliationConfig:
    reconciliation_interval_sec: int = 30
    position_mismatch_tolerance_pct: float = 0.1
    order_timeout_sec: int = 300
    enable_auto_correction: bool = False
    event_cache_size: int = 10000
    alert_on_mismatch: bool = True
```

## 失敗モードと対策

### 部分約定の不適切な処理
- 対策: 累積約定数量追跡、完全約定までポジション更新を遅延

### 重複イベント
- 対策: 処理済みイベントIDキャッシュ、trade_idベースの重複排除

### 順序逆転
- 対策: タイムスタンプベースの順序保証、状態整合性チェック

### 通信断によるイベント欠落
- 対策: 定期的な取引所状態同期、不一致検出

### 再起動後の状態消失
- 対策: 永続化、取引所状態との照合、手動修正プロンプト

## テスト観点

### 単体テスト
- 注文状態遷移の正確性
- 累積約定計算の正確性
- 重複イベント排除
- 順序逆転対応

### 統合テスト
- Binance testnetとの実際の注文ライフサイクル
- 部分約定シナリオ
- 通信断復旧シナリオ
- 再起動復旧シナリオ

### カオステスト
- ランダムなイベント順序
- 重複イベントの注入
- 通信断シミュレーション

### パフォーマンステスト
- 大量注文処理
- 長時間稼働のメモリ使用量
- イベント処理レイテンシー

## モニタリングと観測性

### メトリクス
- `reconciliation_pending_orders_count`
- `reconciliation_unfilled_orders_count`
- `reconciliation_mismatch_count`
- `reconciliation_fill_latency_ms`
- `reconciliation_event_processing_rate`

### ログ
- 注文状態遷移の詳細ログ
- 約定イベントの詳細ログ
- 整合性チェック結果
- 不一致検出時のアラート

### GUI表示
- 注文ライフサイクルの可視化
- 保留中注文の状態表示
- 整合性チェック結果の表示
- 不一致アラートの表示

## 既存コンポーネントとの統合

### Gateway
- 実行イベント受信時にリコンサイラーを呼び出す
- ACKイベントではFillEventを生成しない
- 約定イベントでのみFillEventを生成

### PositionManager
- リコンサイラーからのみFillEventを受け取る
- 既存のポジション管理ロジックは変更なし

### Monitor
- 整合性メトリクスを収集
- 定期的な整合性チェックを実行
- アラート生成

### GUI
- 注文ライフサイクルダッシュボードを追加
- 整合性状態のリアルタイム表示

## 実装優先順位

### Phase 30A: 基礎コンポーネント
1. OrderLifecycle状態マシン
2. Fill Tracker
3. 基本的なReconciler

### Phase 30B: Gateway統合
1. GatewayへのReconciler統合
2. イベントフローの修正
3. 基本的なテスト

### Phase 30C: 高度な機能
1. 定期整合性チェック
2. 再起動復旧
3. GUIダッシュボード
4. カオステスト

## 受入基準

### 機能要件
- ACKイベントでポジションが更新されないこと
- 部分約定が正確に追跡されること
- 完全約定時のみポジションが更新されること
- 重複イベントが適切に処理されること
- 整合性チェックが正しく機能すること

### 品質要件
- 単体テストカバレッジ > 90%
- 統合テストがすべてパスすること
- 既存のテストが regression なしでパスすること
- コードレビューが承認されていること

### 運用要件
- 再起動後の復旧が自動で成功すること
- 不一致検出時に適切なアラートが発報されること
- GUIで状態が正しく表示されること
- パフォーマンスが許容範囲内であること

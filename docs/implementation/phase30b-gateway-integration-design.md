# Phase 30B: Gateway統合設計

- Date: 2026-06-18
- Phase: 30B - Gateway統合
- Status: 設計中

## 既存Gatewayコードの分析結果

### 現在のアーキテクチャ
```
Gateway → OrderEvent (注文状態のみ)
         ↓
    (誰かがFillEventに変換)
         ↓
PositionManager ← FillEvent (ポジション更新)
```

### Gatewayの現在の挙動
1. **注文送信**: GatewayはOrderRequestを受け取り、取引所に注文を送信
2. **ACK処理**: 取引所からのACKを受信するとOrderEvent(status="ack")を返す
3. **FillEvent生成**: Gatewayは直接FillEventを生成しない
4. **apply_fill_update**: OrderEventを更新してpartial_filled/filledステータスを設定

### 問題点
- ACKイベントの時点で誰かがFillEventを生成してポジションを更新している（推測）
- ポジション更新のタイミングが不正確
- 部分約定の追跡が不十分

## 統合戦略

### 基本方針
**Gateway自体には大きな変更を加えず、ExecutionReconcilerをGatewayとPositionManagerの間に配置**

### 新しいアーキテクチャ
```
Gateway → OrderEvent (注文状態のみ)
         ↓
ExecutionBridge (OrderEvent → ExecutionEvent変換)
         ↓
ExecutionReconciler (実行整合性処理)
         ↓
FillEvent (適切なタイミングで生成)
         ↓
PositionManager ← FillEvent (ポジション更新)
```

### コンポーネント設計

#### 1. ExecutionBridge
**役割**: OrderEventをExecutionEventに変換

```python
class ExecutionBridge:
    def convert_order_event(self, order_event: OrderEvent) -> ExecutionEvent | None:
        """OrderEventをExecutionEventに変換"""
        # statusによって適切なEventTypeをマッピング
        # ack → ORDER_ACK
        # partial_filled → ORDER_PARTIAL_FILLED
        # filled → ORDER_FILLED
        # rejected → ORDER_REJECTED
        # canceled → ORDER_CANCELLED
```

#### 2. GatewayIntegrationLayer
**役割**: GatewayとExecutionReconcilerの統合

```python
class GatewayIntegrationLayer:
    def __init__(self, gateway: OrderGateway, reconciler: ExecutionReconciler):
        self.gateway = gateway
        self.reconciler = reconciler
        self.bridge = ExecutionBridge()

    def submit_with_reconciliation(
        self, req: OrderRequest, **kwargs
    ) -> tuple[OrderEvent, PositionFillEvent | None]:
        """注文送信と実行整合性処理"""
        # 1. Gatewayで注文送信
        order_event = self.gateway.submit(req, **kwargs)

        # 2. 保留中注文をリコンサイラーに登録
        if order_event.status == "ack":
            self.reconciler.register_pending_order(...)

        # 3. OrderEventをExecutionEventに変換して処理
        exec_event = self.bridge.convert_order_event(order_event)
        if exec_event:
            fill_event = self.reconciler.process_execution_event(exec_event)
        else:
            fill_event = None

        return order_event, fill_event
```

### 実装ステップ

#### Step 1: ExecutionBridgeの実装
- OrderEventからExecutionEventへの変換ロジック
- ステータスマッピング（ack → ORDER_ACKなど）
- フィールドマッピング

#### Step 2: GatewayIntegrationLayerの実装
- GatewayとExecutionReconcilerの統合
- 保留中注文の自動登録
- FillEventコールバック処理

#### Step 3: 既存コードとの統合
- worker/runner.pyでの使用
- 既存のFillEvent生成ロジックの置き換え
- 設定ファイルの更新

#### Step 4: テスト
- 単体テスト（ExecutionBridge）
- 統合テスト（GatewayIntegrationLayer）
- 回帰テスト（既存機能）

### 変更の影響範囲

#### 変更が必要なファイル
1. `src/auto_trader/execution/bridge.py` (新規)
2. `src/auto_trader/execution/integration.py` (新規)
3. `src/auto_trader/worker/runner.py` (既存コード修正)
4. 設定ファイル (オプション)

#### 変更が不要なファイル
1. `src/auto_trader/exchange/gateway.py` (既存コード維持)
2. `src/auto_trader/position/manager.py` (既存コード維持)

### リスクと緩和策

#### リスク
1. **既存のワークフローとの互換性**: 既存コードがGatewayのOrderEventを直接使用している可能性
2. **パフォーマンス**: 追加のレイヤーによる処理遅延
3. **複雑性**: アーキテクチャの複雑化

#### 緩和策
1. **段階的な導入**: 最初はオプション機能として導入
2. **パフォーマンス監視**: メトリクスによる遅延監視
3. **明確なインターフェース**: シンプルなAPI設計

### 成功基準

#### 機能要件
- ACKイベントでFillEventが生成されないこと
- 完全約定時のみFillEventが生成されること
- 部分約定が正確に追跡されること
- 既存のGateway機能が維持されること

#### 品質要件
- 単体テストカバレッジ > 90%
- 既存テストの回帰なし
- パフォーマンスが許容範囲内

### 実装スケジュール

#### Week 1
- ExecutionBridge実装と単体テスト
- GatewayIntegrationLayer実装と単体テスト

#### Week 2
- worker/runner.pyとの統合
- 統合テスト実装
- 回帰テスト実行

#### Week 3
- パフォーマンス最適化
- ドキュメント更新
- 本番環境へのデプロイ準備

## 結論

Gatewayコードへの影響を最小限にしつつ、ExecutionReconcilerを統合する設計が完了しました。このアプローチにより、段階的な導入と安全性が確保されます。

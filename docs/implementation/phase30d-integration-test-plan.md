# Phase 30D: 統合テスト実装計画

- Date: 2026-06-18
- Phase: 30D - 統合テスト実装
- Status: 計画中

## 目的

ExecutionReconciler有効時の完全な統合テストを実装し、実行整合性サービスが本番運用で正しく機能することを検証する。

## 現状

### 実装済み機能
- **Phase 30A**: 基礎コンポーネント（単体テスト完備）
- **Phase 30B**: Gateway統合ブリッジ層（単体テスト完備）
- **Phase 30C**: Worker統合（オプション実装、回帰テスト完備）

### 未実装機能
- **実行イベント処理**: WebSocketからの実行イベントをExecutionReconcilerに統合
- **統合テストシナリオ**: 有効時の完全な統合テスト
- **回帰テスト（有効時）**: 既存テストが有効時もパスすることの検証

## 統合テスト計画

### Step 1: 実行イベント処理の統合

**対象**: `worker/runner.py` の `_try_process_execution_fill_delta` メソッド

**現在の実装**:
- WebSocket実行イベント → 直接FillEvent生成 → PositionManager

**目標実装**:
- WebSocket実行イベント → OrderEvent変換 → GatewayIntegrationLayer → ExecutionReconciler → FillEvent

**アプローチ**:
```python
def _try_process_execution_fill_delta(self, ...):
    # 既存の実行イベント処理ロジック

    # ExecutionReconcilerが有効な場合、統合レイヤーを通す
    if self.execution_integration_layer is not None:
        # ExecutionStreamEventをOrderEventに変換
        order_event = self._convert_execution_stream_to_order_event(event, order_row)
        fill_event = self.execution_integration_layer.process_existing_order_event(order_event)
        # FillEventはコールバックで処理される
    else:
        # 従来のフロー（_apply_execution_fill_delta）
```

### Step 2: ExecutionStreamEvent → OrderEvent変換

**新規メソッド**: `_convert_execution_stream_to_order_event`

**機能**:
- WebSocketのExecutionStreamEventをGatewayのOrderEventに変換
- 適切なフィールドマッピング
- ステータスの適切な設定

### Step 3: 統合テストシナリオ

#### シナリオ1: ACKイベント処理
**目的**: ACKイベントでFillEventが生成されないことを確認
- 注文送信 → ACK受信
- FillEventが生成されないこと
- 保留中注文が正しく登録されること

#### シナリオ2: 完全約定イベント処理
**目的**: 完全約定でのみFillEventが生成されることを確認
- 注文送信 → 完全約定イベント
- FillEventが正確に生成されること
- ポジションが正しく更新されること

#### シナリオ3: 部分約定イベント処理
**目的**: 部分約定の累積追跡を確認
- 注文送信 → 部分約定イベント（複数回）
- 最終的に完全約定時にFillEventが生成されること
- 累積約定数量が正確であること

#### シナリオ4: 重複イベント処理
**目的**: 重複実行イベントが適切に処理されることを確認
- 同一実行イベントの重複送信
- 重複排除が機能すること
- FillEventが重複生成されないこと

#### シナリオ5: 状態永続化と復旧
**目的**: 再起動後の状態復旧を確認
- 注文中に再起動
- 再起動後に状態が正しく復旧すること
- 実行イベントが正しく処理されること

### Step 4: 回帰テスト（有効時）

**対象**: 既存のworkerテスト（`test_worker_runner.py`）

**アプローチ**:
- テストフィクスチャーでExecutionReconcilerを有効化して実行
- 既存テストがすべてパスすることを確認
- テスト結果の比較検証

## 実装ステップ

### Week 1: 実行イベント処理統合
1. `_convert_execution_stream_to_order_event` メソッド実装
2. `_try_process_execution_fill_delta` の統合修正
3. 単体テスト実装

### Week 2: 短期統合テスト
1. シナリオ1-2の実装（ACK、完全約定）
2. 短期統合テスト実装
3. 結果検証

### Week 3: 高度な統合テスト
1. シナリオ3-5の実装（部分約定、重複、復旧）
2. 長期統合テスト実装
3. 回帰テスト（有効時）

## 成功基準

### 機能要件
- ACKイベントでFillEventが生成されないこと
- 完全約定時のみFillEventが生成されること
- 部分約定が正確に追跡されること
- 重複イベントが適切に処理されること
- 再起動後の状態復旧が正しく機能すること

### 品質要件
- 統合テストカバレッジ > 80%
- 回帰テスト（有効時）のパス率 100%
- 既存テスト（無効時）の回帰維持
- コード品質チェック（mypy/ruff）パス

### 運用要件
- 有効/無効の切り替えがスムーズであること
- パフォーマンスへの影響が許容範囲内であること
- エラー発生時に適切なフォールバックが機能すること

## リスクと緩和策

### リスク
1. **実行イベント変換の複雑性**: ExecutionStreamEvent → OrderEvent変換の正確性
2. **パフォーマンス**: 追加レイヤーによる処理遅延
3. **状態不一致**: 既存フローと新フローの状態同期

### 緩和策
1. **慎重な変換実装**: 既存の変換ロジックを参考に実装
2. **パフォーマンス監視**: メトリクスによる遅延監視
3. **段階的導入**: オプション機能として安全に導入

## 結論

ExecutionReconciler有効時の完全な統合テストを実装し、本番運用での安全性と信頼性を検証します。

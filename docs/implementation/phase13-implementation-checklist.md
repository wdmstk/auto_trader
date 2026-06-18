# Phase 13 実装チェックリスト（Streamlit GUI）

## 実装項目
- [x] ダッシュボード主要パネル実装（PnL/Regime/Exposure/Risk/API）
- [x] decision summary 実装（現在状態 / 直近異常 / 次の推奨アクション）
- [x] 操作ボタン実装（START/STOP/EMERGENCY系）
- [x] チャートoverlay実装（regime/entry/exit/ml/risk）
- [x] 操作イベントログ表示実装
- [x] Trading タブの route / state / block reason 集約表示
- [x] 同一 symbol の複数 route 表示対応
- [x] staleデータ警告実装
- [x] control bridge 実装（GUI event -> runtime handler）
- [x] runtime state反映実装（control_state.json）
- [x] runtime watch実装（`python -m auto_trader.runtime --watch`）

## UI/UX改善（2026-06-18）
- [x] 緊急制御の視覚的階層改善（通常制御と緊急制御の分離）
- [x] 緊急操作に確認ダイアログ追加（誤操作防止）
- [x] 持続的ステータスバナー実装（EMERGENCY/HIGH_VOL状態の強調表示）
- [x] デシジョンサマリーの視覚的強化（ヘルスレベルに応じた表示）
- [x] 古いデータ警告の改善（経過時間と閾値の明示）
- [x] Tradingタブの視覚的インジケーター追加（ステータス絵文字、ルート種別表示）
- [x] UIスタイルの全般的改善（メトリクスカード、ボタンスタイル、データフレーム可読性）

## Done定義
- [x] 緊急ボタンが常時表示される
- [x] ボタン操作が監査ログに残る
- [x] HIGH_VOL/EMERGENCYが視覚的に識別できる
- [x] ユニット/統合テストが通る
- [x] 緊急操作に確認ダイアログが表示される
- [x] ステータスが持続的バナーで即座に識別できる

## レビュー観点
1. 誤操作を誘発しないUI配置であること
2. 状態遅延が明示されること
3. 運用者が停止判断を即時に行えること
4. Overview と Trading の役割が重複しすぎないこと
5. route key ベースの worker state を誤読なく表示できること
6. 緊急状態が一目で識別できること（改善済み）
7. 重要なデシジョン情報が優先的に表示されること（改善済み）

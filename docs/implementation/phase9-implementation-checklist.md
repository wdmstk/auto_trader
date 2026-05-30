# Phase 9 実装チェックリスト（Stress Testing）

## 実装項目
- [x] baselineバックテスト実行機能
- [x] volatility 2x シナリオ実装
- [x] flash crash シナリオ実装
- [x] low liquidity シナリオ実装
- [x] spread widening シナリオ実装
- [x] API timeout シナリオ実装
- [x] シナリオ比較レポート出力

## Done定義
- [x] 5シナリオが独立に再現実行できる
- [x] baseline差分（PF/DD/MonthlyPnL）が算出される
- [x] failure_count が記録される
- [x] catastrophic劣化ケースを検知できる
- [x] ユニット/統合テストが通る

## レビュー観点
1. シナリオ変形が価格/コストへ実際に反映されること
2. 指標比較が同条件（期間/資金）で行われること
3. 障害イベントの記録漏れがないこと

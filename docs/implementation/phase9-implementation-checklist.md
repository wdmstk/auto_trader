# Phase 9 実装チェックリスト（Stress Testing）

## 実装項目
- [ ] baselineバックテスト実行機能
- [ ] volatility 2x シナリオ実装
- [ ] flash crash シナリオ実装
- [ ] low liquidity シナリオ実装
- [ ] spread widening シナリオ実装
- [ ] API timeout シナリオ実装
- [ ] シナリオ比較レポート出力

## Done定義
- [ ] 5シナリオが独立に再現実行できる
- [ ] baseline差分（PF/DD/MonthlyPnL）が算出される
- [ ] failure_count が記録される
- [ ] catastrophic劣化ケースを検知できる
- [ ] ユニット/統合テストが通る

## レビュー観点
1. シナリオ変形が価格/コストへ実際に反映されること
2. 指標比較が同条件（期間/資金）で行われること
3. 障害イベントの記録漏れがないこと

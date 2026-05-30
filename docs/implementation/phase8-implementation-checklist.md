# Phase 8 実装チェックリスト（Backtesting）

## 実装項目
- [ ] 約定シミュレーター（entry/exit）
- [ ] feeモデル実装
- [ ] slippageモデル実装
- [ ] spreadモデル実装
- [ ] execution delayモデル実装
- [ ] equity/DD/月次集計実装
- [ ] 成績サマリ出力実装（PF/Expectancy等）

## Done定義
- [ ] fee/slippage/spread/delay がPnLへ反映される
- [ ] `pass_filter=false` を約定対象外にできる
- [ ] HIGH_VOL停止がバックテストでも有効
- [ ] MaxDDを再計算して一致する
- [ ] ユニット/統合テストが通る

## レビュー観点
1. optimistic fill（楽観約定）になっていないこと
2. DD計算がバー更新順で一貫すること
3. コスト二重計上/未計上がないこと

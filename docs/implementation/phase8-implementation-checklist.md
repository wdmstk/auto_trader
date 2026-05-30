# Phase 8 実装チェックリスト（Backtesting）

## 実装項目
- [x] 約定シミュレーター（entry/exit）
- [x] feeモデル実装
- [x] slippageモデル実装
- [x] spreadモデル実装
- [x] execution delayモデル実装
- [x] equity/DD/月次集計実装
- [x] 成績サマリ出力実装（PF/Expectancy等）

## Done定義
- [x] fee/slippage/spread/delay がPnLへ反映される
- [x] `pass_filter=false` を約定対象外にできる
- [x] HIGH_VOL停止がバックテストでも有効
- [x] MaxDDを再計算して一致する
- [x] ユニット/統合テストが通る

## レビュー観点
1. optimistic fill（楽観約定）になっていないこと
2. DD計算がバー更新順で一貫すること
3. コスト二重計上/未計上がないこと

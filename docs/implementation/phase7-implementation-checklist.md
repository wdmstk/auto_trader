# Phase 7 実装チェックリスト（ML Pipeline）

## 実装項目
- [x] dataset builder（features/regime/signal/label結合）
- [x] split生成（train/valid/test、時系列順）
- [x] binary classifier学習（初期LightGBM）
- [x] calibration/threshold最適化
- [x] walkforward評価
- [x] 推論フィルタ（pass_filter）実装

## Done定義
- [x] no shuffle/no leakage を自動検証
- [x] dataset重複/欠損キー検知がある
- [x] walkforward指標（PF/Expectancy/DD）を出力
- [x] `pass_filter` が安定して再現可能

## レビュー観点
1. 目的が方向予測へ逸脱していないこと
2. 時系列分割を破る処理がないこと
3. 閾値最適化が test を汚染していないこと

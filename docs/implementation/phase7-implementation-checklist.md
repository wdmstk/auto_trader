# Phase 7 実装チェックリスト（ML Pipeline）

## 実装項目
- [ ] dataset builder（features/regime/signal/label結合）
- [ ] split生成（train/valid/test、時系列順）
- [ ] binary classifier学習（初期LightGBM）
- [ ] calibration/threshold最適化
- [ ] walkforward評価
- [ ] 推論フィルタ（pass_filter）実装

## Done定義
- [ ] no shuffle/no leakage を自動検証
- [ ] dataset重複/欠損キー検知がある
- [ ] walkforward指標（PF/Expectancy/DD）を出力
- [ ] `pass_filter` が安定して再現可能

## レビュー観点
1. 目的が方向予測へ逸脱していないこと
2. 時系列分割を破る処理がないこと
3. 閾値最適化が test を汚染していないこと

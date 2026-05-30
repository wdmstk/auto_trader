# Phase 7 Spec: ML Pipeline

- Version: 1.0
- Date: 2026-05-30
- Related ADR: 0001, 0003

## 目的
Regime/Strategyで抽出した候補シグナルを、期待値フィルタとしてMLで選別する。

## 入力（I/O契約）
- 特徴量テーブル（Phase 2）
- Regime判定テーブル（Phase 3）
- ラベルテーブル（Phase 4）
- 戦略シグナル（Phase 5/6）

## 出力（I/O契約）
- 学習データセット
  - 主キー: `(symbol, timeframe, timestamp)`
  - `features`, `label`, `sample_weight`, `split`
- 学習済みモデル
  - `model_version`, `feature_version`, `train_range`, `metrics`
- 推論スコア
  - `ml_score`, `threshold`, `pass_filter`

## 前提条件
- 目的は「方向予測」ではなく「低期待値セットアップ除外」。
- 時系列splitのみ許可（no shuffle）。
- ラベルはTP/SL先着2値のみ。

## 仕様
1. Dataset Builder
- features/regime/signal/labelを同一キーで内部結合。
- 欠損/重複キーは学習対象から除外し監査ログへ記録。

2. 学習
- 初期モデル: LightGBM分類器（binary）。
- 学習範囲: 時系列train/valid/test。
- キャリブレーションと閾値最適化を実施。

3. WalkForward
- 推奨: 6m train / 2m valid / 2m test。
- 各窓でPF/Expectancy/DDを記録。

4. 推論
- `pass_filter = ml_score >= threshold`。
- `pass_filter=false` は発注前に停止。

## 失敗モードと対策
- leakage混入: キー整合と時系列検証で失敗。
- 指標過学習: walkforward安定性で弾く。
- モデル/特徴量バージョン不一致: 推論停止。

## テスト観点
- no shuffle/no leakage が自動検証されること。
- dataset key整合（重複/欠損）検知。
- walkforward分割が時系列順になること。
- threshold適用で pass_filter が決定されること。

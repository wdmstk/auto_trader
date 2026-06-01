# Phase 28 Spec: Volatility-Weighted Exposure / Risk Contribution

- Version: 1.0
- Date: 2026-06-01
- Related ADR: 0001, 0002

## 目的
相関集中時の同時損失を抑制するため、単純相関だけでなく
ボラティリティ加重エクスポージャーとリスク寄与度制御を導入する。

## 入力（I/O契約）
- symbol別エクスポージャー
- symbol別ボラティリティ（rolling）
- 相関行列（rolling）
- ポートフォリオ許容閾値

## 出力（I/O契約）
- symbol別 `risk_contribution_pct`
- `vol_weighted_exposure_pct`
- ブロック判定: `RISK_VOL_WEIGHTED_EXPOSURE`
- 推奨縮小率: `size_scale`

## 前提条件
- 既存 `max_correlated_exposure_pct` 判定は維持する。
- 新判定は補助ではなく、閾値超過時は新規建て抑止可能とする。

## 仕様
1. 指標計算
- rolling volatility を用いて exposure を重み付けする。
- 相関行列を使って portfolio risk contribution を算出する。

2. 制御
- 閾値超過時は `size_scale < 1.0` を適用するか、新規建てを拒否する。
- 急激なvol上昇銘柄は優先的に縮小対象とする。

3. 可観測性
- GUI/レポートに risk contribution 上位銘柄を表示する。
- 週次再評価に `vol_weighted_exposure` の推移を保存する。

## 失敗モードと対策
- 相関1.0近傍集中: 単一閾値でなく段階制御を採用。
- 欠損データ: 安全側縮小または建て禁止。
- 過剰縮小: 最低取引サイズ閾値を定義し運用可能性を維持。

## テスト観点
- vol急増銘柄で自動縮小が動作する。
- 閾値超過で block reason が返る。
- 既存相関ゲートとの整合が保たれる。

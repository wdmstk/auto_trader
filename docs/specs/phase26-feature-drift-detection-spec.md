# Phase 26 Spec: Feature Drift Detection / PSI Monitoring

- Version: 1.0
- Date: 2026-06-01
- Related ADR: 0001, 0003

## 目的
バックテスト時特徴量分布と本番特徴量分布の乖離を検知し、
ドリフト時の警告と取引抑止判断を可能にする。

## 入力（I/O契約）
- バックテスト基準統計: featureごとの `mean`, `std`, `histogram bins`
- 本番オンライン統計: rolling window の `mean`, `std`, `histogram bins`
- 対象feature一覧

## 出力（I/O契約）
- feature単位ドリフト指標: `psi`, `mean_delta_z`, `std_ratio`
- 集約判定: `status=pass|warn|fail`
- ゲート連携信号: `drift_trade_block=true|false`

## 前提条件
- regime/risk/runtime gate を最優先し、本判定は追加安全層として扱う。
- ドリフト判定は即時停止ではなく閾値ベースの段階判定とする。

## 仕様
1. 統計集計
- featureごとにオンライン統計を更新する。
- 比較対象は同一feature定義・同一変換後値とする。

2. ドリフト指標
- `PSI` を一次指標とする。
- 補助として `mean_delta_z`, `std_ratio` を保存する。

3. 判定基準（初期）
- `psi < 0.1`: pass
- `0.1 <= psi < 0.25`: warn
- `psi >= 0.25`: fail

4. 運用動作
- `warn`: GUI警告 + 週次再評価の優先度上げ
- `fail`: `is_trade_allowed=false` 相当の追加ブロックを許可

## 失敗モードと対策
- 基準統計が欠落: `unknown` として安全側 `warn`。
- 欠損値急増: feature品質異常として別イベント記録。
- 単一feature誤判定: 集約判定は閾値超過feature比率も併用。

## テスト観点
- PSIが閾値境界で正しく `pass/warn/fail` 遷移する。
- `fail` 時に取引抑止フラグが立つ。
- 統計欠落時に安全側判定になる。

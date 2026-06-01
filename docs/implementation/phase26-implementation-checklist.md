# Phase 26 実装チェックリスト（Feature Drift Detection）

## 実装前に固定する事項
- [x] 集約判定ルール（例: fail feature比率しきい値）を定義
  - 初期値: `fail feature比率 >= 0.30` で `status=fail`、`>=0.10` で `status=warn`
- [x] `unknown`（基準統計欠落）時の扱いを固定（warn固定/条件付きfail）
  - 初期値: 単一feature欠落は `warn`、`欠落比率 >= 0.30` は `fail`
- [x] GUI表示粒度（feature別詳細/集約のみ）を固定
  - 初期値: デフォルトは集約表示、`show details` トグルでfeature別詳細を表示
- [x] baseline統計の保存フォーマットを固定
  - 初期値: `data/validation/drift/baseline_stats.json`（feature単位: mean/std/histogram_bins）

## 実装項目
- [x] バックテスト基準統計の保存導線を追加
- [x] 本番オンライン統計の集計導線を追加
- [x] PSI / mean_delta_z / std_ratio 計算実装
- [x] drift status（pass/warn/fail）判定実装
- [x] GUI警告表示導線を追加
- [x] `is_trade_allowed` 連携のブロック条件を実装
- [x] ユニットテストを追加

## Done定義
- [x] 基準統計と本番統計を比較できる
- [x] PSI閾値で `pass/warn/fail` が再現する
- [x] 集約判定ルールどおりに最終statusが決定される
- [x] `fail` 時に取引抑止が有効になる
- [x] 週次再評価レポートへ drift 状態を残せる
- [x] spec-review を作成済み

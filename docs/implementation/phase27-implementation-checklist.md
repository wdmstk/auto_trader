# Phase 27 実装チェックリスト（Limit/Maker Cost Optimization）

## 実装前に固定する事項
- [x] partial fill 残数量ポリシー（cancel固定/次バー繰越）を固定
  - 初期値: v1は `cancel固定`（次バー繰越はv2候補）
- [x] limit約定条件（タッチ/滞留）の保守的判定ルールを固定
  - 初期値: `high/low` タッチのみでは約定扱いにしない。`1 bar` 滞留で `filled` 判定
- [x] maker前提崩壊の判定閾値（taker化率）を固定
  - 初期値: `taker化率 > 0.40` で `warn`、`> 0.60` で `fail`

## 実装項目
- [x] backtest入力へ order_mode（market/limit）追加
- [x] maker/taker fee 設定の分離
- [x] limit約定判定ロジック（filled/partial/expired）追加
- [x] partial fill 後の状態遷移実装
- [x] cost grid レポートへ order_mode 指標追加
- [x] candidate/weekly report へ limit evidence summary を反映
- [x] market 本線 / limit 診断の理由情報を report に反映
- [x] route-centric candidate schema（`route_counts` / `symbol_counts` / shadow routes）を導入
- [x] `weekly_core_feedback.json` を route 正本として追加
- [x] worker 入力 `selection.trade_routes` を複数同一-symbol route 対応へ拡張
- [x] ユニット/統合テストを追加
- [x] 実注文経路（exchange）へ order_type（market/limit）導線を追加
  - `LIMIT` は `IOC` 固定（未約定は cancel 扱い）
  - `market` 互換は既定値として維持
  - live worker の既定運用は `trend=market`, `range=market` とする
- [x] 約定モデルv2（板厚/queue近似）を backtest/analysis に追加
  - `limit_book_depth_units` / `limit_queue_ahead_units` / `limit_volume_participation_rate`
  - 既定値は `0`（互換維持、旧ロジックを踏襲）

## Done定義
- [x] market と limit で比較可能なレポートを出力できる
- [x] gross/net/cost内訳が一貫する
- [x] partial fill 状態整合性テストが通る
- [x] order_mode 次元を含む cost grid 比較ができる
- [x] route 件数と symbol 件数が report 上で混同されない
- [x] worker が同一 symbol の複数 route を live 反映できる
- [x] spec-review を作成済み

## 次PR候補（約定モデル強化）
- [ ] execution report を position / order_events / GUI へ反映し、取引所の `expired/canceled/partial/filled` を local state と一致させる
- [ ] queue_ahead の時間減衰（bar経過で先行数量を減衰）
- [ ] GTC近似（最大Nバー持ち越し）モデルの追加
- [ ] 銘柄別 depth/queue 初期値プロファイル化
- [x] limit 実績集計（filled/partial/expired/canceled, taker-like rate）を週次レポートへ反映

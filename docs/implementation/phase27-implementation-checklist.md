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
- [x] ユニット/統合テストを追加
- [x] 実注文経路（exchange）へ order_type（market/limit）導線を追加
  - `LIMIT` は `IOC` 固定（未約定は cancel 扱い）
  - `market` 互換は既定値として維持

## Done定義
- [x] market と limit で比較可能なレポートを出力できる
- [ ] gross/net/cost内訳が一貫する
- [x] partial fill 状態整合性テストが通る
- [x] order_mode 次元を含む cost grid 比較ができる
- [x] spec-review を作成済み

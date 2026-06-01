# Phase 27 実装チェックリスト（Limit/Maker Cost Optimization）

## 実装前に固定する事項
- [x] partial fill 残数量ポリシー（cancel固定/次バー繰越）を固定
  - 初期値: v1は `cancel固定`（次バー繰越はv2候補）
- [x] limit約定条件（タッチ/滞留）の保守的判定ルールを固定
  - 初期値: `high/low` タッチのみでは約定扱いにしない。`1 bar` 滞留で `filled` 判定
- [x] maker前提崩壊の判定閾値（taker化率）を固定
  - 初期値: `taker化率 > 0.40` で `warn`、`> 0.60` で `fail`

## 実装項目
- [ ] backtest入力へ order_mode（market/limit）追加
- [ ] maker/taker fee 設定の分離
- [ ] limit約定判定ロジック（filled/partial/expired）追加
- [ ] partial fill 後の状態遷移実装
- [ ] cost grid レポートへ order_mode 指標追加
- [ ] ユニット/統合テストを追加

## Done定義
- [ ] market と limit で比較可能なレポートを出力できる
- [ ] gross/net/cost内訳が一貫する
- [ ] partial fill 状態整合性テストが通る
- [ ] order_mode 次元を含む cost grid 比較ができる
- [ ] spec-review を作成済み

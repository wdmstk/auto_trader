# Phase 27 Spec: Limit Order / Maker Cost Optimization

- Version: 1.0
- Date: 2026-06-01
- Related ADR: 0001, 0002

## 目的
成行主体で発生しているコスト負けを抑制するため、
指値（maker寄り）約定モデルと評価指標を導入する。

## 入力（I/O契約）
- シグナル（entry/exit）
- 約定モデル入力: price, spread, slippage仮定, delay
- 取引コスト設定: maker/taker fee

## 出力（I/O契約）
- 注文種別別結果: `market|limit`
- 約定判定: `filled|partial|expired|canceled`
- コスト内訳: `fee_cost`, `spread_cost`, `impact_cost`
- 評価指標: `gross_pnl`, `net_pnl`, `expectancy_bps`

## 前提条件
- 既存のリスクゲートとruntimeゲートは不変。
- 初期はシミュレーション評価を優先し、本番投入は段階導入。

## 仕様
1. 注文モード
- 既存 market モードを維持。
- limit モードを追加し、maker手数料仮定を適用可能にする。

2. 約定モデル
- 価格到達/滞留条件で `filled/partial/expired` を判定。
- partial fill の残数量は cancel または次バー繰越を選択可能にする。

3. 評価軸
- grossが正でもnetが負になるケースを明示検知。
- cost sensitivity（fee/slippage/spread/delay）をレポートする。

## 失敗モードと対策
- 過度な楽観約定: 到達条件を保守的に設定。
- partial fill 状態不整合: 注文状態遷移ログを必須化。
- maker前提崩壊: taker化率を監視し閾値超過時warn。

## テスト観点
- limit/marketの切替が正しく機能する。
- partial/expired/canceled 遷移が整合する。
- コスト内訳が net pnl と一致する。

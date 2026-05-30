# Phase 8 Spec: Backtesting

- Version: 1.0
- Date: 2026-05-30
- Related ADR: 0001, 0002, 0003

## 目的
実運用を過度に楽観しない検証環境として、コスト・遅延・約定不確実性を含むバックテストを実行する。

## 入力（I/O契約）
- 市場データ（OHLCV）
- 戦略シグナル（Phase 5/6）
- MLフィルタ結果（Phase 7）
- リスク制約設定

## 出力（I/O契約）
- 約定履歴テーブル
  - `timestamp, symbol, side, price, size, fee, slippage, status`
- ポートフォリオ履歴テーブル
  - `equity, cash, position_value, drawdown`
- 評価指標
  - `PF, Expectancy, WinRate, MaxDD, MonthlyPnL`

## 前提条件
- fee/slippage/spread/delay を全て考慮する。
- `pass_filter=false` のシグナルは約定対象外。
- `HIGH_VOL` 停止ルールをバックテストでも強制する。

## 仕様
1. コストモデル
- 取引所手数料を売買ごとに適用
- slippageは流動性係数で調整
- spreadをエントリー/エグジット双方に適用

2. 実行遅延
- シグナル発生から `n` バー遅延約定を設定可能にする。
- 遅延約定時は当該バー価格レンジ内で保守的に約定評価。

3. ポートフォリオ評価
- equityカーブを時系列出力
- MaxDDを逐次更新
- 月次PnLを集計

4. 失敗/除外
- データ欠損区間は取引停止
- リスク上限違反シグナルは失効

## 失敗モードと対策
- コスト未反映: 実運用乖離を生むため失敗扱い。
- 遅延未反映: 約定幻想を生むため失敗扱い。
- DD計算不整合: 検証停止と再計算。

## テスト観点
- fee/slippage/spread/delayがPnLへ反映されること。
- `pass_filter=false` が約定しないこと。
- HIGH_VOL時に新規建てしないこと。
- MaxDD計算が再現可能であること。

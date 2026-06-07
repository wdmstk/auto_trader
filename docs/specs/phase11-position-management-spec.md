# Phase 11 Spec: Position Management

- Version: 1.0
- Date: 2026-05-30
- Related ADR: 0001, 0002

## 目的
建玉を安全に管理し、平均取得単価・追加建玉・エクスポージャを一貫管理する。

## 入力（I/O契約）
- 約定イベント（Phase 10）
- 戦略シグナル（Phase 5/6）
- リスク制約

## 出力（I/O契約）
- ポジション状態テーブル
  - `symbol, strategy, timeframe, route_key, side, qty, avg_entry, unrealized_pnl_pct, add_count, updated_at`
- エクスポージャ状態
  - `symbol_exposure_pct, portfolio_exposure_pct, correlation_bucket`

## 前提条件
- add/pyramidはTREND方針に従い、含み益時のみ許可。
- `risk_blocked=true` の場合は建玉追加禁止。
- 異常時（不整合約定）は安全側で建玉縮小または停止。

## 仕様
1. 平均取得単価
- 約定ごとに加重平均で更新。
- 反対売買で部分クローズ時は残数量に応じて再計算。

2. add管理
- `add_count` を銘柄別に保持。
- 上限超過時は追加拒否。

3. エクスポージャ管理
- symbol別/portfolio全体の比率を毎イベント更新。
- positionは `route_key = strategy:symbol:timeframe` 単位で保持し、同一symbolの複数routeを分離する。
- symbol exposureは同一symbolに属する全routeのnotionalを合算する。
- 閾値超過時に `risk_blocked` を引き上げる。

4. 永続化と後方互換
- 新規保存時は `strategy/timeframe/route_key` を必須列として保存する。
- 旧schemaにroute列がない場合は `legacy:<symbol>:15m` として読み込む。
- migration時に旧positionを破棄せず、次回保存時に新schemaへ更新する。

## 失敗モードと対策
- 約定欠損: ポジション再構築ジョブで補正。
- avg_entry不整合: 再計算と差異アラート。
- exposure過小評価: 保守的計算に倒す。
- route列欠損: legacy routeへ正規化して読み込みを継続する。

## テスト観点
- 平均取得単価更新が正しいこと。
- add_count上限が効くこと。
- exposure計算が再現可能であること。
- 同一symbolの複数routeが独立して更新され、symbol exposureでは合算されること。
- 旧schemaをlegacy routeとして復旧できること。

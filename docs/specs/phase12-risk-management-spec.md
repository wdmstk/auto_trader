# Phase 12 Spec: Risk Management

- Version: 1.0
- Date: 2026-05-30
- Related ADR: 0001, 0002

## 目的
資本保全を最優先し、DD・エクスポージャ・相関集中を常時計測して危険状態で即時停止する。

## 入力（I/O契約）
- ポジション状態（Phase 11）
- ポートフォリオ履歴（Phase 8）
- シグナル/発注要求（Phase 5/6/10）

## 出力（I/O契約）
- リスク判定テーブル
  - `timestamp, symbol, risk_blocked, block_reason_codes`
- 全体状態
  - `current_dd_pct, portfolio_exposure_pct, concentration_score, emergency_state`

## 前提条件
- DD上限違反時は新規建て停止。
- symbol/portfolio exposure上限違反時は追加建玉停止。
- 緊急停止（emergency_state）は手動解除まで維持可能にする。

## 仕様
1. DD制御
- `current_dd_pct` をバー毎に更新。
- `current_dd_pct > max_dd_pct` で `risk_blocked=true`。

2. エクスポージャ制御
- symbol別とportfolio全体の上限を独立判定。
- 上限超過時は `block_reason_codes` へ記録。

3. 相関集中制御
- 同方向集中を `concentration_score` で表現。
- 閾値超過時は新規建て停止。

4. 緊急停止
- `EMERGENCY_STOP` で新規発注停止。
- `EMERGENCY_CANCEL/CLOSE_ALL` 連携時の状態遷移を保持。

## 失敗モードと対策
- DD算出遅延: stale値なら安全側停止。
- exposure過小評価: 保守的丸めで上振れ検知。
- 緊急状態漏れ: 状態マシンで単一ソース管理。

## テスト観点
- DD閾値超過で block すること。
- exposure閾値超過で block すること。
- emergency_state で発注停止すること。
- reason_codes が必ず出ること。

# Phase 13 Spec: Streamlit GUI

- Version: 1.0
- Date: 2026-05-30
- Related ADR: 0001, 0002

## 目的
運用安全を高めるため、状態可視化と緊急操作を一画面で提供する。

## 入力（I/O契約）
- regime/position/risk/execution 各状態テーブル
- 監視メトリクス（DD, exposure, API status, latency）
- 操作コマンド（START/STOP/EMERGENCY系）

## 出力（I/O契約）
- ダッシュボードUI
  - `PnL`, `Regime`, `Exposure`, `Risk`, `API`
- 操作イベントログ
  - `action, requested_at, applied_at, result`
- Runtime制御状態
  - `data/runtime/control_state.json`
  - `trading_enabled, emergency_stop, close_all_requested, updated_at`

## 前提条件
- GUIは装飾目的でなく、運用判断と誤操作防止が主目的。
- 緊急ボタンは常時表示。
- HIGH_VOL/EMERGENCY状態は強調表示。

## 仕様
1. Dashboard
- PnL/DD推移、現在regime、ポジション一覧、exposure一覧を表示。

2. Controls
- `START`, `STOP`, `EMERGENCY_STOP`, `EMERGENCY_CANCEL`, `CLOSE_ALL` を提供。
- 操作イベントは `data/gui/control_events.jsonl` へ追記し、runtime watcher が反映する。

3. Visualization
- ローソク足 + regime overlay + entry/exit overlay。
- ML score と risk block 状態を同時表示。

## 失敗モードと対策
- stale表示: 更新時刻を明示し閾値超過で警告。
- 操作反映失敗: 再送導線 + 失敗理由表示。
- 緊急操作誤発火: 確認ダイアログを必須化。

## テスト観点
- ボタン操作が対応イベントを発行すること。
- 操作イベントが runtime handler に伝播し `control_state.json` が更新されること。
- stale状態を警告できること。
- HIGH_VOL/EMERGENCYが視覚的に識別可能であること。

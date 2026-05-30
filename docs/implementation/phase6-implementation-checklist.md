# Phase 6 実装チェックリスト（TREND Strategy）

## 実装項目
- [x] TREND戦略エントリー条件を実装
- [x] TREND戦略エグジット条件を実装
- [x] Regimeゲート連携（TREND以外停止）を実装
- [x] HIGH_VOL強制停止連携を実装
- [x] Pyramid（add）条件と上限管理を実装
- [x] risk_blocked抑止を実装
- [x] signal_reason_codes出力を実装

## Done定義
- [x] TREND以外で `entry_signal=true` が発生しない
- [x] HIGH_VOLで `entry_signal/add_signal=false` を保証
- [x] `risk_blocked=true` で `entry_signal/add_signal=false` を保証
- [x] reason_codesの欠損がない
- [x] ユニット/統合テストが通る

## レビュー観点
1. Regime gate回避の抜け道がないこと
2. HIGH_VOL停止が最優先で効くこと
3. add/pyramidの回数制御が効くこと

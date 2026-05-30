# Phase 5 実装チェックリスト（RANGE Strategy）

## 実装項目
- [x] RANGE戦略エントリー条件を実装
- [x] RANGE戦略エグジット条件を実装
- [x] Regimeゲート連携（RANGE以外停止）を実装
- [x] HIGH_VOL強制停止連携を実装
- [x] risk_blocked抑止とサイズ算出を実装
- [x] signal_reason_codes出力を実装

## Done定義
- [x] RANGE以外で `entry_signal=true` が発生しない
- [x] `risk_blocked=true` 行で `entry_signal=false` を保証
- [x] reason_codesの欠損がない
- [x] ユニット/統合テストが通る

## レビュー観点
1. Regime gate回避の抜け道がないこと
2. HIGH_VOL停止が最優先で効くこと
3. リスク上限違反時の停止が優先されること

# Phase 5 実装チェックリスト（RANGE Strategy）

## 実装項目
- [ ] RANGE戦略エントリー条件を実装
- [ ] RANGE戦略エグジット条件を実装
- [ ] Regimeゲート連携（RANGE以外停止）を実装
- [ ] HIGH_VOL強制停止連携を実装
- [ ] risk_blocked抑止とサイズ算出を実装
- [ ] signal_reason_codes出力を実装

## Done定義
- [ ] RANGE以外で `entry_signal=true` が発生しない
- [ ] `risk_blocked=true` 行で `entry_signal=false` を保証
- [ ] reason_codesの欠損がない
- [ ] ユニット/統合テストが通る

## レビュー観点
1. Regime gate回避の抜け道がないこと
2. HIGH_VOL停止が最優先で効くこと
3. リスク上限違反時の停止が優先されること

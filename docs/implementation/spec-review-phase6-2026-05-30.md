# Specレビュー結果（Phase 6）

- Date: 2026-05-30
- Scope: `phase6-trend-strategy-spec.md`
- Reviewer: Codex

## 結論
Phase 6（TREND Strategy）は実装前仕様として、Regime gate・high vol停止・pyramid制御を固定できた。

## 固定事項
1. Regime連携
- `regime == TREND` かつ `is_trade_allowed == true` 以外はentry禁止。
- `HIGH_VOL` は `TR_BLOCK_HIGH_VOL` で停止。

2. リスク抑止
- `risk_blocked=true` で `entry_signal/add_signal=false` 強制。
- add回数上限を必須化。

3. 説明可能性
- `signal_reason_codes` を必須化し、entry/exit/add/blockの根拠を残す。

## 残留リスク
- breakout系はダマシに弱いため、walkforwardで閾値調整が必要。
- トレンド終盤の高値掴みを避けるため、Phase 7でMLフィルタ連携が必要。

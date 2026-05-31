# Longrun Validation Record

- Date: 2026-05-31 (JST)
- Operator: Codex (wdmstk)
- Issue: https://github.com/wdmstk/auto_trader/issues/8
- Method: 短時間ドライラン（反復実行 + 異常系再現）
- Raw record: `/tmp/issue8_validation/record.json`

## Window
- 2026-05-31T03:41:51Z - 2026-05-31T03:41:53Z

## Scope
- runtime state durability (`control_state.json`)
- notify state durability (`notify_state.json`)

## Scenario Results
- Normal run: `pass`
  - runtime `updated_at` 更新確認: `true`
  - runtime lock残留なし: `true`（`runtime_lock_residual=false`）
  - runtime backup存在: `true`
  - notify lock残留なし: `true`（`notify_lock_residual=false`）
  - notify backup存在: `true`
- Corruption recovery: `pass`
  - runtime primary破損後に読み戻し継続: `true`
  - notify primary破損後もdispatch継続: `true`
- Lock contention: `pass`
  - runtime lock競合時 timeout検知: `true`
  - notify lock競合時 timeout検知: `true`

## Notes
- 本記録は「実証手順と異常系の基本成立確認」を目的とした短時間実行。
- Issue #8 の完了条件である「通常連続運転（8時間以上）」は未達のため、次回実行で本記録を追補する。

## Decision
- Conditional Go（実証基盤は有効、長時間運転証跡が未充足）

# 長時間連続運転 実証プレイブック（Issue #8）

- Version: 1.0
- Date: 2026-05-31
- Related Issue: https://github.com/wdmstk/auto_trader/issues/8

## 目的
本番運用Go判定に必要な、長時間連続運転の実証計画・実施・証跡記録を標準化する。

## 対象範囲
- Runtime watcher: `python -m auto_trader.runtime --watch`
- Notify watcher: `python -m auto_trader.notify --from-env --watch`
- Ops watcher: `python -m auto_trader.ops --watch`
- State durability監視:
  - `data/runtime/control_state.json(.lock/.bak)`
  - `data/ops/notify_state.json(.lock/.bak)`

## 事前準備チェック
- [ ] `full/smoke/validate-gates` が直近green
- [ ] `config/config.prod.yaml` に本番相当設定を反映
- [ ] runtime/notify/ops の運用手順が現行ドキュメントと一致
- [ ] 監視用ログ保存先を確保（最低48時間分）

## 事前セットアップ（必須）
`RUNTIME_STATE_INVALID` と `RISK_DATA_INVALID` を防ぐため、watch開始前に実施する。

```bash
cd /home/komug/projects/auto_trader
. .venv/bin/activate

# runtime state 初期化
mkdir -p data/runtime data/gui
: > data/gui/control_events.jsonl
python -m auto_trader.runtime --max-iterations 1

# risk input/eval 初期化
mkdir -p data/risk
python - << 'PY'
import pandas as pd
from datetime import datetime, timezone
pd.DataFrame([{
  "timestamp": datetime.now(timezone.utc).isoformat(),
  "symbol": "BTCUSDT",
  "current_equity": 1000.0,
  "equity_peak": 1000.0,
  "symbol_exposure_pct": 10.0,
  "portfolio_exposure_pct": 20.0,
  "concentration_score": 0.3
}]).to_parquet("data/risk/risk_input.parquet", index=False)
PY
python -m auto_trader.risk \
  --input-path data/risk/risk_input.parquet \
  --output-path data/risk/risk_eval.parquet
```

確認コマンド:
```bash
ls -l data/runtime/control_state.json data/risk/risk_eval.parquet
```

## 実証シナリオ
1. 通常連続運転（8時間以上）
- 目的: watcher停止やstate異常なく連続稼働できることを確認する。
- 実施:
  - runtime/notify/ops を watch モードで起動
  - 30分ごとに `updated_at`, `.lock` 残留, `.bak` 更新有無を確認
- 合格:
  - `.lock` が長時間残留しない
  - `updated_at` が定期更新される
  - エラーで処理停止しない

2. 異常系A（state破損）
- 目的: primary破損時に backup recovery が機能することを確認する。
- 実施:
  - `control_state.json` または `notify_state.json` を意図的に破損
  - 次サイクルで処理継続可否と復旧挙動を確認
- 合格:
  - 処理がクラッシュせず継続
  - `.bak` からの読み戻し相当の挙動が観測できる

3. 異常系B（lock競合）
- 目的: 競合時に破壊的上書きせず、タイムアウト/再試行方針で安全側動作することを確認する。
- 実施:
  - lockファイルを疑似的に残留させる
  - watcherログで timeout 系エラーと回復手順を確認
- 合格:
  - stateファイルの破損が起きない
  - lock解除後に処理が再開できる

## 証跡テンプレート
以下を1実証単位で記録する。

```md
### Longrun Validation Record
- Date: YYYY-MM-DD
- Operator: Codex (wdmstk)
- Window: HH:MM-HH:MM (JST)
- Scope: runtime / notify / ops
- Scenario:
  - Normal run: pass/fail
  - Corruption recovery: pass/fail
  - Lock contention: pass/fail
- Evidence Links:
  - CI run:
  - Log files:
  - Screenshot / snippet:
- Incidents:
  - none / details
- Decision:
  - Go / Conditional Go / No-Go
```

## 失敗時の最小対応
1. 該当watcher停止
2. stateファイル退避（`*.json`, `*.bak`, `*.lock`）
3. 単発実行で再現確認
4. Issue #8 に事象・暫定対応・再発防止案を追記

## 完了条件（Issue #8連動）
- [ ] 通常連続運転の記録を1回以上残す
- [ ] 異常系A/Bの結果を記録し、復旧可否を明示する
- [ ] Issue #8 に証跡リンクを集約する

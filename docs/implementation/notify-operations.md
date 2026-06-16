# Notify 運用ガイド（Phase 16）

- Version: 1.1
- Date: 2026-05-31
- Related Spec: phase16-notify-operations-spec.md

## 目的
通知チャネル連携を本番で安全に稼働させるための設定・疎通確認・常駐化手順を定義する。

## 環境変数
- `AUTO_TRADER_NOTIFY_SLACK_WEBHOOK_URL`
- `AUTO_TRADER_NOTIFY_WEBHOOK_URL`
- `AUTO_TRADER_NOTIFY_SMTP_HOST`
- `AUTO_TRADER_NOTIFY_SMTP_PORT`
- `AUTO_TRADER_NOTIFY_EMAIL_FROM`
- `AUTO_TRADER_NOTIFY_EMAIL_TO`（`,` 区切り）

Slackのみを有効化する最小構成:
```bash
cp ops/env/notify.env.example ops/env/notify.env
$EDITOR ops/env/notify.env
set -a
. ops/env/notify.env
set +a
```

- `AUTO_TRADER_NOTIFY_SLACK_WEBHOOK_URL` に Slack Incoming Webhook URL を設定する。
- URL は Git 管理に含めない。`ops/env/notify.env` はローカル配置専用とする。

## 疎通試験
```bash
python -m auto_trader.notify --from-env --test-alert
```

Slackのみを試験する場合の期待値:
- `channel=slack`
- `success=true`
- `response_code=200`

失敗時の一次切り分け:
- `response_code=401/403`: Webhook URL 不正または無効化
- `response_code=404`: URL 破損
- `error_reason=network_error`: ネットワーク疎通または名前解決失敗

## 常駐運用
```bash
python -m auto_trader.notify --from-env --watch --interval-sec 5 --output-dir data/ops
```

## Durability方針
- `notify_state.json` は `atomic write + lock file + backup recovery` で更新される。
- lock取得失敗時はタイムアウトで失敗し、状態ファイルは保全される。
- stale な `.lock` は PID / 経過時間で回収して再試行する。
- primary破損時は `notify_state.json.bak` から復旧を試行する。

## systemd 例
- テンプレート: `ops/systemd/auto-trader-notify.service.example`
- user service テンプレート: `ops/systemd/auto-trader-notify.user.service.example`

system service（sudo あり、OS起動時に常駐）:
```bash
sudo cp ops/systemd/auto-trader-notify.service.example /etc/systemd/system/auto-trader-notify.service
sudo cp ops/env/notify.env.example /home/komug/projects/auto_trader/ops/env/notify.env
sudoedit /home/komug/projects/auto_trader/ops/env/notify.env
sudo systemctl daemon-reload
sudo systemctl enable --now auto-trader-notify.service
sudo systemctl status auto-trader-notify.service
```

user service（sudo なし、`systemctl --user` で常駐）:
```bash
mkdir -p ~/.config/systemd/user
cp ops/systemd/auto-trader-notify.user.service.example ~/.config/systemd/user/auto-trader-notify.service
cp ops/env/notify.env.example ops/env/notify.env
$EDITOR ops/env/notify.env
systemctl --user daemon-reload
systemctl --user enable --now auto-trader-notify.service
systemctl --user status auto-trader-notify.service
```

- `systemctl --user` では `WantedBy=multi-user.target` は使わない。`default.target` を使う。
- 既に `~/.config/systemd/user/auto-trader-notify.service` を作っている場合は、`[Install]` を `WantedBy=default.target` に修正してから `daemon-reload` を実行する。

## cron 例
```cron
* * * * * cd /home/komug/projects/auto_trader && ./.venv/bin/python -m auto_trader.notify --from-env --output-dir data/ops >> data/ops/notify_cron.log 2>&1
```

## 監視ポイント
- `data/ops/notifications.jsonl` が更新されること
- `success=false` が増加していないこと
- `alert_code=NOTIFY_CHANNEL_DEGRADED` が発生していないこと
- `data/ops/notify_state.json.lock` が長時間残留していないこと
- `data/ops/notify_state.json.bak` が存在し、更新追従していること

## 自動復旧確認
user service の `Restart=always` 確認:
```bash
systemctl --user status auto-trader-notify.service
kill -9 "$(systemctl --user show -p MainPID --value auto-trader-notify.service)"
sleep 5
systemctl --user status auto-trader-notify.service
journalctl --user -u auto-trader-notify.service -n 20 --no-pager
```

判定基準:
- 停止前後とも `Loaded: loaded` を維持していること
- `kill -9` 後、5秒以内を目安に `Active: active (running)` へ復帰すること
- `journalctl` に `Scheduled restart job` または再起動後の `Started auto-trader-notify.service` が記録されること
- 復帰後に `216/GROUP`, `ModuleNotFoundError`, `network_error` が連続していないこと

補足:
- `MainPID` が `0` の場合は service が既に停止しているため、先に `systemctl --user restart auto-trader-notify.service` を実行する。
- 本確認は watcher プロセスを意図的に落とすため、相場監視中に実施する場合は影響時間を把握したうえで行う。

## 障害時切り分け
1. `--test-alert` でチャネル個別疎通確認
2. 環境変数の設定値・有効期限確認
3. service/cron の実行ログ確認

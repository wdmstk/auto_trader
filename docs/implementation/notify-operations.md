# Notify 運用ガイド（Phase 16）

- Version: 1.0
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

## 疎通試験
```bash
python -m auto_trader.notify --from-env --test-alert
```

## 常駐運用
```bash
python -m auto_trader.notify --from-env --watch --interval-sec 5 --output-dir data/ops
```

## systemd 例
- テンプレート: `ops/systemd/auto-trader-notify.service.example`

```bash
sudo cp ops/systemd/auto-trader-notify.service.example /etc/systemd/system/auto-trader-notify.service
sudo systemctl daemon-reload
sudo systemctl enable --now auto-trader-notify.service
sudo systemctl status auto-trader-notify.service
```

## cron 例
```cron
* * * * * cd /home/komug/projects/auto_trader && ./.venv/bin/python -m auto_trader.notify --from-env --output-dir data/ops >> data/ops/notify_cron.log 2>&1
```

## 監視ポイント
- `data/ops/notifications.jsonl` が更新されること
- `success=false` が増加していないこと
- `alert_code=NOTIFY_CHANNEL_DEGRADED` が発生していないこと

## 障害時切り分け
1. `--test-alert` でチャネル個別疎通確認
2. 環境変数の設定値・有効期限確認
3. service/cron の実行ログ確認

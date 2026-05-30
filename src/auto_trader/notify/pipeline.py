from __future__ import annotations

from pathlib import Path

import pandas as pd

from auto_trader.notify.channels import Notifier
from auto_trader.notify.service import NotificationService, NotifyPolicy
from auto_trader.notify.store import NotificationStore


def run_notification_pipeline(
    *,
    alerts_path: str | Path = "data/ops/alerts.parquet",
    notifiers: list[Notifier],
    output_dir: str | Path = "data/ops",
    policy: NotifyPolicy | None = None,
    state_path: str | Path = "data/ops/notify_state.json",
) -> tuple[pd.DataFrame, Path]:
    alerts_df = _read_alerts(Path(alerts_path))
    rows: list[dict[str, str]] = []
    if not alerts_df.empty:
        rows = [
            {str(k): str(v) for k, v in rec.items()} for rec in alerts_df.to_dict(orient="records")
        ]
    service = NotificationService(notifiers=notifiers, policy=policy, state_path=state_path)
    results = service.dispatch(rows)
    out_df = pd.DataFrame(results)
    store = NotificationStore(output_dir)
    saved = store.append(results)
    return out_df, saved


def _read_alerts(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    if path.suffix == ".jsonl":
        return pd.read_json(path, lines=True)
    return pd.read_parquet(path)

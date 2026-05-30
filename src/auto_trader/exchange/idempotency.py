from __future__ import annotations

import hashlib
from datetime import datetime


def build_client_order_id(
    *,
    symbol: str,
    side: str,
    signal_ts: datetime,
    strategy: str,
    nonce: str = "",
) -> str:
    raw = f"{strategy}|{symbol}|{side}|{signal_ts.isoformat()}|{nonce}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"cid_{digest}"

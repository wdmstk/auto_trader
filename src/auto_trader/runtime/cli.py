from __future__ import annotations

import argparse
import json
from pathlib import Path

from auto_trader.runtime.control import process_control_events_once


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Process GUI control events once.")
    p.add_argument("--control-log-path", default="data/gui/control_events.jsonl")
    p.add_argument("--cursor-path", default="data/runtime/control_cursor.json")
    p.add_argument("--state-path", default="data/runtime/control_state.json")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    result = process_control_events_once(
        control_log_path=Path(args.control_log_path),
        cursor_path=Path(args.cursor_path),
        state_path=Path(args.state_path),
    )
    print(json.dumps({"processed": result.processed, "actions": result.actions}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

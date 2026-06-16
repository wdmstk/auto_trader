from __future__ import annotations

from pathlib import Path

import yaml

REQUIRED_CHECKS = {"coverage", "full", "smoke"}


def validate_required_checks(workflow_path: str | Path) -> tuple[bool, list[str], list[str]]:
    path = Path(workflow_path)
    if not path.exists():
        return False, [], sorted(REQUIRED_CHECKS)
    with path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}
    jobs = payload.get("jobs", {})
    if not isinstance(jobs, dict):
        return False, [], sorted(REQUIRED_CHECKS)
    actual = [str(k) for k in jobs.keys()]
    missing = sorted(REQUIRED_CHECKS - set(actual))
    return len(missing) == 0, sorted(actual), missing

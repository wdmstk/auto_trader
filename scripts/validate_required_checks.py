from __future__ import annotations

import json
from pathlib import Path

from auto_trader.ci.required_checks import validate_required_checks


def main() -> int:
    ok, actual, missing = validate_required_checks(Path(".github/workflows/ci.yml"))
    print(json.dumps({"ok": ok, "actual": actual, "missing": missing}, ensure_ascii=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

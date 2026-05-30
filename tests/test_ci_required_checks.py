from __future__ import annotations

from pathlib import Path

from auto_trader.ci.required_checks import validate_required_checks


def test_validate_required_checks_passes_with_current_ci() -> None:
    ok, actual, missing = validate_required_checks(Path(".github/workflows/ci.yml"))
    assert ok is True
    assert "full" in actual
    assert "smoke" in actual
    assert missing == []


def test_validate_required_checks_fails_when_missing(tmp_path: Path) -> None:
    wf = tmp_path / "ci.yml"
    wf.write_text(
        "name: CI\njobs:\n  full:\n    runs-on: ubuntu-latest\n    steps: []\n",
        encoding="utf-8",
    )
    ok, _, missing = validate_required_checks(wf)
    assert ok is False
    assert "smoke" in missing

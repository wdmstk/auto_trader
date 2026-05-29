from __future__ import annotations

from pathlib import Path

import pytest

from auto_trader.config import RuntimeMode, load_settings


def test_load_local_config_success() -> None:
    settings = load_settings(Path("config/config.local.yaml"))
    assert settings.system.mode == RuntimeMode.DRY_RUN
    assert settings.exchange.margin_type == "isolated"


def test_production_mode_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    with pytest.raises(ValueError, match="production mode requires credentials"):
        load_settings(Path("config/config.prod.yaml"))


def test_system_mode_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_TRADER_SYSTEM_MODE", "testnet")
    settings = load_settings(Path("config/config.local.yaml"))
    assert settings.system.mode == RuntimeMode.TESTNET

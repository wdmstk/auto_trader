from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class Env(StrEnum):
    LOCAL = "local"
    CI = "ci"
    PROD = "prod"


class RuntimeMode(StrEnum):
    DRY_RUN = "dry_run"
    TESTNET = "testnet"
    PRODUCTION = "production"


class LoggingLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class SystemConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    env: Env
    mode: RuntimeMode


class ExchangeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = "binance"
    margin_type: str = "isolated"
    max_leverage: int = Field(ge=1, le=3)

    @field_validator("margin_type")
    @classmethod
    def margin_type_must_be_isolated(cls, value: str) -> str:
        if value != "isolated":
            raise ValueError("exchange.margin_type must be isolated")
        return value


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_risk_per_trade_pct: float = Field(gt=0.0, le=1.0)
    max_symbol_exposure_pct: float = Field(gt=0.0, le=100.0)
    max_portfolio_exposure_pct: float = Field(gt=0.0, le=100.0)
    max_drawdown_pct: float = Field(gt=0.0, le=100.0)


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    emergency_stop_enabled: bool = True


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enable_reconciliation: bool = False
    reconciliation_state_path: str = "data/execution/reconciliation_state.json"


class StrategyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    range: dict[str, Any] = {}
    trend: dict[str, Any] = {}


class LoggingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: LoggingLevel = LoggingLevel.INFO
    jsonl_path: str


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system: SystemConfig
    exchange: ExchangeConfig
    risk: RiskConfig
    runtime: RuntimeConfig
    execution: ExecutionConfig = ExecutionConfig()
    strategy: StrategyConfig = StrategyConfig()
    logging: LoggingConfig

    @model_validator(mode="after")
    def validate_production_requirements(self) -> Settings:
        if self.system.mode == RuntimeMode.PRODUCTION:
            required = ["BINANCE_API_KEY", "BINANCE_API_SECRET"]
            missing = [key for key in required if not os.getenv(key)]
            if missing:
                raise ValueError("production mode requires credentials: " + ", ".join(sorted(missing)))
        return self


def load_settings(config_path: str | Path) -> Settings:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    merged = apply_env_overrides(data)
    try:
        return Settings.model_validate(merged)
    except ValidationError as exc:
        raise ValueError(f"invalid config: {exc}") from exc


def apply_env_overrides(config_data: dict[str, Any]) -> dict[str, Any]:
    data = dict(config_data)
    mode_override = os.getenv("AUTO_TRADER_SYSTEM_MODE")
    env_override = os.getenv("AUTO_TRADER_SYSTEM_ENV")
    if mode_override:
        data.setdefault("system", {})
        data["system"]["mode"] = mode_override
    if env_override:
        data.setdefault("system", {})
        data["system"]["env"] = env_override
    return data

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    DUPLICATE_CLIENT_ORDER_ID = "DUPLICATE_CLIENT_ORDER_ID"
    STALE_SIGNAL = "STALE_SIGNAL"
    GATING_BLOCKED = "GATING_BLOCKED"
    RUNTIME_TRADING_DISABLED = "RUNTIME_TRADING_DISABLED"
    RUNTIME_EMERGENCY_STOP = "RUNTIME_EMERGENCY_STOP"
    RUNTIME_STATE_INVALID = "RUNTIME_STATE_INVALID"
    RATE_LIMIT = "RATE_LIMIT"
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT = "TIMEOUT"
    SERVER_ERROR = "SERVER_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class GatewayError(Exception):
    def __init__(self, code: ErrorCode, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


class RateLimitError(GatewayError):
    pass


class NetworkError(GatewayError):
    pass


class TimeoutGatewayError(GatewayError):
    pass


class ServerGatewayError(GatewayError):
    pass


class UnknownGatewayError(GatewayError):
    pass


def gateway_error_from_code(code: ErrorCode, reason: str) -> GatewayError:
    if code == ErrorCode.RATE_LIMIT:
        return RateLimitError(code, reason)
    if code == ErrorCode.NETWORK_ERROR:
        return NetworkError(code, reason)
    if code == ErrorCode.TIMEOUT:
        return TimeoutGatewayError(code, reason)
    if code == ErrorCode.SERVER_ERROR:
        return ServerGatewayError(code, reason)
    return UnknownGatewayError(code, reason)

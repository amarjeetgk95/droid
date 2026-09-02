"""
Broker Capability Registry & Rate Limiting Guardrails — Sections 14, 15, 78
Defines official broker capabilities, rate limits, WebSocket limits, authentication rules,
and derives safe internal operational limits (70-80% of broker ceiling).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class BrokerCapabilities:
    broker_name: str
    environment: str
    api_version: str
    orders_per_second: int
    requests_per_second: int
    requests_per_minute: int
    requests_per_day: int
    websocket_symbol_limit: int
    websocket_connection_limit: int
    supported_order_types: List[str]
    static_ip_required: bool
    totp_2fa_required: bool
    token_expiry_hours: float
    trading_hours_start: str = "09:15"
    trading_hours_end: str = "15:30"
    safe_rate_limit_ratio: float = 0.75  # 75% headroom (Sec 15)

    @property
    def internal_orders_per_second(self) -> float:
        return max(1.0, self.orders_per_second * self.safe_rate_limit_ratio)

    @property
    def internal_requests_per_second(self) -> float:
        return max(1.0, self.requests_per_second * self.safe_rate_limit_ratio)

    @property
    def internal_requests_per_minute(self) -> float:
        return max(10.0, self.requests_per_minute * self.safe_rate_limit_ratio)


class BrokerCapabilityRegistry:
    """
    Central repository of broker operational constraints. Strategy and EMS consume this.
    """

    def __init__(self) -> None:
        self._registry: Dict[str, BrokerCapabilities] = {
            "fyers": BrokerCapabilities(
                broker_name="fyers",
                environment="production",
                api_version="v3",
                orders_per_second=10,
                requests_per_second=20,
                requests_per_minute=200,
                requests_per_day=100000,
                websocket_symbol_limit=500,
                websocket_connection_limit=1,
                supported_order_types=["MARKET", "LIMIT", "STOP", "STOP_LIMIT"],
                static_ip_required=False,
                totp_2fa_required=True,
                token_expiry_hours=24.0,
            ),
            "groww": BrokerCapabilities(
                broker_name="groww",
                environment="production",
                api_version="v1",
                orders_per_second=10,
                requests_per_second=25,
                requests_per_minute=300,
                requests_per_day=100000,
                websocket_symbol_limit=300,
                websocket_connection_limit=2,
                supported_order_types=["MARKET", "LIMIT", "STOP", "STOP_LIMIT"],
                static_ip_required=False,
                totp_2fa_required=True,
                token_expiry_hours=24.0,
            ),
            "upstox": BrokerCapabilities(
                broker_name="upstox",
                environment="production",
                api_version="v2",
                orders_per_second=10,
                requests_per_second=20,
                requests_per_minute=250,
                requests_per_day=100000,
                websocket_symbol_limit=500,
                websocket_connection_limit=1,
                supported_order_types=["MARKET", "LIMIT", "SL", "SL-M"],
                static_ip_required=False,
                totp_2fa_required=True,
                token_expiry_hours=24.0,
            ),
            "kotak_neo": BrokerCapabilities(
                broker_name="kotak_neo",
                environment="production",
                api_version="v1",
                orders_per_second=10,
                requests_per_second=20,
                requests_per_minute=200,
                requests_per_day=100000,
                websocket_symbol_limit=200,
                websocket_connection_limit=1,
                supported_order_types=["MARKET", "LIMIT", "SL", "SL-M"],
                static_ip_required=False,
                totp_2fa_required=True,
                token_expiry_hours=24.0,
            ),
            "binance": BrokerCapabilities(
                broker_name="binance",
                environment="production",
                api_version="v3",
                orders_per_second=50,
                requests_per_second=100,
                requests_per_minute=1200,
                requests_per_day=1000000,
                websocket_symbol_limit=1024,
                websocket_connection_limit=5,
                supported_order_types=["MARKET", "LIMIT", "STOP_LOSS", "TAKE_PROFIT"],
                static_ip_required=False,
                totp_2fa_required=True,
                token_expiry_hours=8760.0,
                trading_hours_start="00:00",
                trading_hours_end="23:59",
            ),
            "paper": BrokerCapabilities(
                broker_name="paper",
                environment="simulation",
                api_version="v1",
                orders_per_second=1000,
                requests_per_second=2000,
                requests_per_minute=50000,
                requests_per_day=10000000,
                websocket_symbol_limit=10000,
                websocket_connection_limit=10,
                supported_order_types=["MARKET", "LIMIT", "MARKETABLE_LIMIT", "STOP", "STOP_LIMIT", "IOC"],
                static_ip_required=False,
                totp_2fa_required=False,
                token_expiry_hours=99999.0,
                trading_hours_start="00:00",
                trading_hours_end="23:59",
            ),
        }

    def get(self, broker_name: str) -> BrokerCapabilities:
        key = broker_name.lower().strip()
        if key not in self._registry:
            # Fallback to conservative default
            return BrokerCapabilities(
                broker_name=key,
                environment="unknown",
                api_version="v1",
                orders_per_second=5,
                requests_per_second=10,
                requests_per_minute=100,
                requests_per_day=50000,
                websocket_symbol_limit=100,
                websocket_connection_limit=1,
                supported_order_types=["MARKET", "LIMIT"],
                static_ip_required=False,
                totp_2fa_required=True,
                token_expiry_hours=24.0,
            )
        return self._registry[key]

    def all_capabilities(self) -> Dict[str, BrokerCapabilities]:
        return dict(self._registry)


# Global Singleton
broker_capability_registry = BrokerCapabilityRegistry()

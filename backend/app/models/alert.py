from typing import Literal
from pydantic import BaseModel, Field

AlertType = Literal[
    "PRICE_LEVEL",
    "PCR_THRESHOLD",
    "MAX_PAIN_SHIFT",
    "VOLATILITY_SQUEEZE",
    "SUPERTREND_FLIP",
    "OI_BUILDUP",
]

AlertCondition = Literal[
    "GREATER_THAN",
    "LESS_THAN",
    "CROSSES_ABOVE",
    "CROSSES_BELOW",
    "EQUALS",
]

NotificationChannel = Literal["IN_APP", "WEBHOOK", "TELEGRAM", "EMAIL"]


class AlertPayload(BaseModel):
    """Payload for creating or updating an alert rule."""
    name: str = Field(min_length=2, max_length=100)
    symbol: str = Field(default="NIFTY")
    alert_type: AlertType = "PRICE_LEVEL"
    condition: AlertCondition = "GREATER_THAN"
    threshold: float
    channel: NotificationChannel = "IN_APP"
    webhook_url: str | None = None


class AlertRule(BaseModel):
    """Configured alert rule."""
    id: str
    name: str
    symbol: str
    alert_type: AlertType
    condition: AlertCondition
    threshold: float
    channel: NotificationChannel
    webhook_url: str | None = None
    is_active: bool = True
    last_triggered: str | None = None
    created_at: str


class AlertTriggerLog(BaseModel):
    """Audit log entry for a triggered alert."""
    id: str
    alert_id: str
    alert_name: str
    symbol: str
    timestamp: str
    triggered_value: float
    threshold_value: float
    message: str
    channel_dispatched: NotificationChannel


class SystemTelemetry(BaseModel):
    """Production system health and worker telemetry."""
    status: Literal["HEALTHY", "DEGRADED", "UNHEALTHY"] = "HEALTHY"
    uptime_seconds: float
    memory_usage_mb: float
    active_workers: dict[str, str] = Field(default_factory=dict)
    stream_latency_ms: float = 12.5
    active_alert_rules_count: int = 0
    total_alerts_triggered: int = 0

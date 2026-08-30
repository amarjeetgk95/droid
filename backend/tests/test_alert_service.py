import pytest
from app.services.alert_service import AlertService
from app.models.alert import AlertPayload


class TestAlertService:
    def test_default_rules_seeded(self):
        service = AlertService()
        rules = service.get_rules()
        assert len(rules) >= 3

    def test_create_and_delete_rule(self):
        service = AlertService()
        payload = AlertPayload(
            name="Test Breakout Alert",
            symbol="BANKNIFTY",
            alert_type="PRICE_LEVEL",
            condition="GREATER_THAN",
            threshold=53000.0,
            channel="IN_APP",
        )
        rule = service.create_rule(payload)
        assert rule.symbol == "BANKNIFTY"
        assert rule.is_active is True

        # Toggle rule
        toggled = service.toggle_rule(rule.id)
        assert toggled.is_active is False

        # Delete rule
        deleted = service.delete_rule(rule.id)
        assert deleted is True

    @pytest.mark.asyncio
    async def test_evaluate_rules(self):
        service = AlertService()
        # Seed an alert that will definitely trigger
        service.create_rule(AlertPayload(
            name="Always Triggered Low Price",
            symbol="NIFTY",
            alert_type="PRICE_LEVEL",
            condition="GREATER_THAN",
            threshold=1000.0,
            channel="IN_APP",
        ))

        triggered = await service.evaluate_rules()
        assert len(triggered) >= 1
        assert len(service.get_history()) >= 1

    def test_system_telemetry(self):
        service = AlertService()
        telemetry = service.get_telemetry()
        assert telemetry.status == "HEALTHY"
        assert telemetry.memory_usage_mb > 0
        assert "central_feed" in telemetry.active_workers

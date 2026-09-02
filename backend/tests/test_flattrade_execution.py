import pytest
import uuid
from decimal import Decimal
from app.algo.execution import (
    broker_registry, FlattradeLiveBrokerAdapter, OrderRecord
)


def test_flattrade_broker_adapter_registered():
    adapter = broker_registry.get("flattrade", paper=False)
    assert adapter.provider_name == "flattrade"
    assert isinstance(adapter, FlattradeLiveBrokerAdapter)


@pytest.mark.asyncio
async def test_flattrade_order_submission_simulation_fallback():
    adapter = FlattradeLiveBrokerAdapter()
    order = OrderRecord(
        account_id="ACC_FT_01",
        client_order_id=uuid.uuid4(),
        symbol="NIFTY24SEP24500CE",
        side="BUY",
        quantity=50,
        price=Decimal("125.50"),
        order_type="LIMIT",
    )
    res = await adapter.submit_order(order)
    assert res["status"] in ("FILLED", "PARTIALLY_FILLED", "SUBMITTED")
    assert "broker_order_id" in res

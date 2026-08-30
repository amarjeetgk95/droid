import pytest
from app.services.paper_service import PaperTradingService
from app.models.paper import OrderPayload, BasketOrderPayload


class TestPaperTradingService:
    @pytest.mark.asyncio
    async def test_place_single_order_and_position(self):
        service = PaperTradingService()
        order_payload = OrderPayload(
            symbol="NIFTY24800CE",
            underlying="NIFTY",
            side="BUY",
            order_type="MARKET",
            product="INTRADAY",
            quantity=75,
            price=150.0,
        )
        order = await service.place_order(order_payload)

        assert order.status == "FILLED"
        assert order.fill_price == 150.0

        positions = await service.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "NIFTY24800CE"
        assert positions[0].quantity == 75

        summary = await service.get_portfolio_summary()
        assert summary.open_positions_count == 1
        assert summary.used_margin > 0

    @pytest.mark.asyncio
    async def test_basket_order_and_square_off(self):
        service = PaperTradingService()
        basket = BasketOrderPayload(
            name="Bull Call Spread",
            orders=[
                OrderPayload(symbol="NIFTY24800CE", underlying="NIFTY", side="BUY", quantity=75, price=150.0),
                OrderPayload(symbol="NIFTY25000CE", underlying="NIFTY", side="SELL", quantity=75, price=60.0),
            ]
        )
        orders = await service.place_basket(basket)
        assert len(orders) == 2
        assert all(o.status == "FILLED" for o in orders)

        # Square off single position
        await service.square_off_position("NIFTY24800CE_INTRADAY")
        positions = await service.get_positions()
        open_pos = [p for p in positions if p.is_open]
        assert len(open_pos) == 1

        # Square off all
        await service.square_off_all()
        summary = await service.get_portfolio_summary()
        assert summary.open_positions_count == 0

    @pytest.mark.asyncio
    async def test_reset_portfolio(self):
        service = PaperTradingService()
        await service.place_order(OrderPayload(symbol="NIFTY24800CE", underlying="NIFTY", side="BUY", quantity=75, price=100.0))
        summary = service.reset_portfolio()
        assert summary.virtual_capital == 1000000.0
        assert summary.open_positions_count == 0
        assert len(service.get_orders()) == 0

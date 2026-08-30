from app.quant.margin import calculate_required_margin


class TestMarginCalculator:
    def test_option_buying_margin(self):
        # Buying 2 lots of NIFTY CE at ₹150 (Quantity = 150)
        margin = calculate_required_margin("OPTION_BUY", "NIFTY", price=150.0, quantity=150)
        assert margin == 150.0 * 150

    def test_option_selling_margin(self):
        # Naked selling 1 lot of NIFTY PE (Quantity = 75)
        margin_naked = calculate_required_margin("OPTION_SELL", "NIFTY", price=150.0, quantity=75, is_hedged=False)
        assert margin_naked == 125000.0

        # Hedged selling 1 lot of NIFTY PE (40% of naked requirement)
        margin_hedged = calculate_required_margin("OPTION_SELL", "NIFTY", price=150.0, quantity=75, is_hedged=True)
        assert margin_hedged == 125000.0 * 0.40

    def test_futures_margin(self):
        margin_fut = calculate_required_margin("FUTURES", "BANKNIFTY", price=52000.0, quantity=25)
        assert margin_fut == 145000.0

from app.quant.costs import calculate_option_costs


class TestOptionCosts:
    def test_option_costs_breakdown(self):
        # 1 lot buy at ₹150, 1 lot sell at ₹200 (Lot size = 75, turnover buy=11250, sell=15000)
        buy_to = 11250.0
        sell_to = 15000.0
        costs = calculate_option_costs(
            buy_turnover=buy_to,
            sell_turnover=sell_to,
            num_orders=2,
            brokerage_per_order=20.0,
            slippage_pct=0.001,
        )

        assert costs.stt == round(sell_to * 0.00125, 2)
        assert costs.exchange_charges == round((buy_to + sell_to) * 0.0005, 2)
        assert costs.brokerage == 40.0
        assert costs.gst > 0
        assert costs.total_cost > costs.brokerage + costs.stt

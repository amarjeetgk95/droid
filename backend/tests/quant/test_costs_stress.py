"""Cost stress testing and BSE SENSEX cost verification (Tier 0)."""

import pytest
from app.quant.costs import calculate_trade_costs, BSE_SENSEX_OPTIONS, BSE_SENSEX_FUTURES, calculate_square_root_slippage


class TestCostStress:

    def test_bse_sensex_options_cost(self):
        # 1 lot buy at ₹150, sell at ₹200 (Lot size = 10, turnover buy=1500, sell=2000)
        buy_to = 1500.0
        sell_to = 2000.0
        costs = calculate_trade_costs(
            buy_turnover=buy_to,
            sell_turnover=sell_to,
            num_orders=2,
            schedule=BSE_SENSEX_OPTIONS,
            slippage_rate=0.001,
            stress_multiplier=1.0,
        )

        assert costs.stt == round(sell_to * 0.00125, 2)
        assert costs.exchange_charges == round((buy_to + sell_to) * 0.0005, 2)
        assert costs.brokerage == 40.0
        assert costs.gst > 0
        assert costs.net_drag_bps > 0

    def test_cost_stress_multipliers(self):
        buy_to = 10000.0
        sell_to = 12000.0
        c_1x = calculate_trade_costs(buy_to, sell_to, schedule=BSE_SENSEX_OPTIONS, stress_multiplier=1.0)
        c_1_5x = calculate_trade_costs(buy_to, sell_to, schedule=BSE_SENSEX_OPTIONS, stress_multiplier=1.5)
        c_2x = calculate_trade_costs(buy_to, sell_to, schedule=BSE_SENSEX_OPTIONS, stress_multiplier=2.0)

        assert c_1_5x.total_cost > c_1x.total_cost * 1.45
        assert c_2x.total_cost > c_1x.total_cost * 1.95

    def test_square_root_slippage_model(self):
        slip_low = calculate_square_root_slippage(order_size=10, available_volume=1000)
        slip_high = calculate_square_root_slippage(order_size=500, available_volume=1000)
        assert slip_high > slip_low

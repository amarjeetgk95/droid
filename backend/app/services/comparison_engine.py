from datetime import datetime, timezone
from app.models.crypto import (
    CryptoPairComparison,
    RelativeStrengthStatus,
)
from app.models.market import DataStatus


class ComparisonEngine:
    """Quantitative relative strength engine comparing Bitcoin (BTC) vs Ethereum (ETH)."""

    @staticmethod
    def calculate_comparison(
        btc_price: float,
        btc_change_pct: float,
        btc_volume_quote: float,
        eth_price: float,
        eth_change_pct: float,
        eth_volume_quote: float,
        eth_btc_direct_price: float | None = None,
        eth_btc_direct_change_pct: float | None = None,
        data_status: DataStatus = DataStatus.LIVE,
    ) -> CryptoPairComparison:
        ratio = eth_btc_direct_price if eth_btc_direct_price else (eth_price / btc_price if btc_price > 0 else 0.0)
        spread = round(eth_change_pct - btc_change_pct, 2)

        if spread > 0.5:
            rel_strength = RelativeStrengthStatus.ETH_OUTPERFORMING
        elif spread < -0.5:
            rel_strength = RelativeStrengthStatus.BTC_OUTPERFORMING
        else:
            rel_strength = RelativeStrengthStatus.NEUTRAL

        ratio_change = eth_btc_direct_change_pct if eth_btc_direct_change_pct is not None else spread
        ratio_delta = round(ratio * (ratio_change / 100.0), 6)

        vol_ratio = round(eth_volume_quote / btc_volume_quote, 3) if btc_volume_quote > 0 else 0.0

        return CryptoPairComparison(
            eth_btc_ratio=round(ratio, 6),
            eth_btc_change_24h=ratio_delta,
            eth_btc_change_percent_24h=round(ratio_change, 2),
            btc_price=round(btc_price, 2),
            btc_change_percent_24h=round(btc_change_pct, 2),
            eth_price=round(eth_price, 2),
            eth_change_percent_24h=round(eth_change_pct, 2),
            performance_spread_24h=spread,
            relative_strength=rel_strength,
            relative_volume_ratio=vol_ratio,
            status=data_status,
            timestamp=datetime.now(timezone.utc),
        )


comparison_engine = ComparisonEngine()

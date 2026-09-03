import time
from datetime import datetime, timezone
from typing import Optional, Tuple
from app.models.crypto import (
    CryptoDerivatives,
    BasisStatus,
    ALLOWED_CRYPTO_SYMBOLS,
)
from app.models.market import DataStatus


class DerivativesEngine:
    """Specialized quantitative engine for BTC & ETH USDT-M Futures analytics."""

    @staticmethod
    def calculate_basis(futures_price: float, spot_price: Optional[float]) -> Tuple[float, float, BasisStatus]:
        """Calculate Spot-Futures Basis and classify Contango vs Backwardation."""
        if not spot_price or spot_price <= 0:
            return 0.0, 0.0, BasisStatus.NEUTRAL

        basis = round(futures_price - spot_price, 2)
        basis_pct = round((basis / spot_price) * 100, 4)

        if basis_pct > 0.01:
            status = BasisStatus.CONTANGO
        elif basis_pct < -0.01:
            status = BasisStatus.BACKWARDATION
        else:
            status = BasisStatus.NEUTRAL

        return basis, basis_pct, status

    @staticmethod
    def calculate_annualized_funding(funding_rate: float) -> float:
        """Annualize 8-hour perpetual funding rate (3 settlements per day * 365 days)."""
        # funding_rate is decimal (e.g. 0.0001 = 0.01%)
        return round(funding_rate * 3 * 365 * 100, 4)

    @staticmethod
    def calculate_countdown(next_funding_time_ms: int) -> int:
        """Calculate remaining countdown seconds to next 8h funding settlement."""
        now_sec = time.time()
        funding_sec = next_funding_time_ms / 1000.0
        return max(0, int(funding_sec - now_sec))

    def build_model(
        self,
        symbol: str,
        mark_price: float,
        index_price: float,
        spot_price: Optional[float],
        funding_rate: float,
        next_funding_time_ms: int,
        open_interest_coins: float,
        long_short_ratio: float,
        long_pct: float,
        short_pct: float,
        top_trader_ratio: Optional[float] = None,
        data_status: DataStatus = DataStatus.LIVE,
    ) -> CryptoDerivatives:
        sym = symbol.upper()
        if sym not in ALLOWED_CRYPTO_SYMBOLS:
            raise ValueError(f"Symbol {sym} not allowed in derivatives engine")

        basis, basis_pct, basis_status = self.calculate_basis(mark_price, spot_price)
        ann_funding = self.calculate_annualized_funding(funding_rate)
        countdown = self.calculate_countdown(next_funding_time_ms)
        oi_usd = round(open_interest_coins * mark_price, 2)
        next_dt = datetime.fromtimestamp(next_funding_time_ms / 1000.0, tz=timezone.utc)

        return CryptoDerivatives(
            symbol=sym,
            mark_price=round(mark_price, 2),
            index_price=round(index_price, 2),
            spot_price=round(spot_price, 2) if spot_price else None,
            basis=basis,
            basis_percent=basis_pct,
            basis_status=basis_status,
            funding_rate=funding_rate,
            funding_rate_percent=round(funding_rate * 100, 4),
            annualized_funding_rate=ann_funding,
            next_funding_time=next_dt,
            countdown_seconds=countdown,
            open_interest_usd=oi_usd,
            open_interest_coins=round(open_interest_coins, 4),
            long_short_ratio=round(long_short_ratio, 2),
            long_percentage=round(long_pct, 2),
            short_percentage=round(short_pct, 2),
            top_traders_long_short_ratio=round(top_trader_ratio, 2) if top_trader_ratio else None,
            status=data_status,
            provider="binance_futures",
            timestamp=datetime.now(timezone.utc),
        )


derivatives_engine = DerivativesEngine()

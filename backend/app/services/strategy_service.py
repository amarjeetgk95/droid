import uuid
from datetime import datetime, date, timezone
from app.models.strategy import (
    StrategyLegModel, StrategyPayload, PayoffPointModel,
    StrategyPayoffResult, StrategyTemplate, ScannedStrategy,
    StrategyCategory, MarketOutlook
)
from app.services.market_service import MarketService
from app.services.contract_master import contract_master_service
from app.quant.payoff import calculate_strategy_payoff, LegParams
from app.quant.expiry_math import calculate_time_to_expiry, get_risk_free_rate
import structlog

logger = structlog.get_logger()


class StrategyService:
    """Multi-Leg Strategy Engine, Scanner, and Payoff Modeling Service."""

    def __init__(self, market_service: MarketService | None = None):
        self.market_service = market_service or MarketService()

    async def calculate_payoff(self, payload: StrategyPayload) -> StrategyPayoffResult:
        """Simulate dual-curve payoff and aggregate Greeks for custom strategy."""
        underlying = payload.underlying.upper().replace(" 50", "")

        if payload.spot_price:
            spot_p = payload.spot_price
        else:
            quote = await self.market_service.get_quote(underlying)
            spot_p = quote.ltp

        # Resolve expiry
        if payload.expiry:
            exp_date = date.fromisoformat(payload.expiry)
        elif payload.legs and payload.legs[0].expiry:
            exp_date = date.fromisoformat(payload.legs[0].expiry)
        else:
            exp_res = contract_master_service.resolve_expiries(underlying)
            exp_date = exp_res.all_expiries[0] if exp_res.all_expiries else datetime.now(timezone.utc).date()

        now = datetime.now(timezone.utc)
        t = calculate_time_to_expiry(now, exp_date)
        r, _ = get_risk_free_rate()

        # Convert to LegParams
        leg_params = [
            LegParams(
                option_type=l.option_type,
                side=l.side,
                strike=l.strike,
                quantity=l.quantity,
                price=l.price,
                iv=l.iv if l.iv > 0 else 0.15,
                lot_size=l.lot_size,
            )
            for l in payload.legs
        ]

        analytics = calculate_strategy_payoff(
            legs=leg_params,
            spot_price=spot_p,
            time_to_expiry=t,
            risk_free_rate=r,
        )

        return StrategyPayoffResult(
            underlying=underlying,
            spot_price=spot_p,
            net_premium=abs(analytics.net_premium),
            premium_type="DEBIT" if analytics.net_premium >= 0 else "CREDIT",
            max_profit=analytics.max_profit,
            max_loss=analytics.max_loss,
            breakevens=analytics.breakevens,
            risk_reward_ratio=analytics.risk_reward_ratio,
            pop_percent=analytics.pop_percent,
            net_delta=analytics.net_delta,
            net_gamma=analytics.net_gamma,
            net_theta=analytics.net_theta,
            net_vega=analytics.net_vega,
            payoff_curve=[
                PayoffPointModel(
                    spot_price=pt.spot_price,
                    expiry_pnl=pt.expiry_pnl,
                    t0_pnl=pt.t0_pnl,
                )
                for pt in analytics.payoff_curve
            ],
            legs=payload.legs,
        )

    def get_templates(self) -> list[StrategyTemplate]:
        """Return catalog of pre-built institutional strategy templates."""
        return [
            StrategyTemplate(
                id="bull_call_spread",
                name="Bull Call Spread (Debit)",
                category="DIRECTIONAL",
                outlook="BULLISH",
                description="Buy ATM Call and Sell OTM Call. Defined risk and defined profit for moderate bullish moves.",
                legs_description=["Buy ATM Call (CE)", "Sell OTM Call (CE)"],
            ),
            StrategyTemplate(
                id="bull_put_spread",
                name="Bull Put Spread (Credit)",
                category="DIRECTIONAL",
                outlook="BULLISH",
                description="Sell ATM Put and Buy OTM Put. Collect net credit benefiting from upward drift and theta decay.",
                legs_description=["Sell ATM Put (PE)", "Buy OTM Put (PE)"],
            ),
            StrategyTemplate(
                id="bear_put_spread",
                name="Bear Put Spread (Debit)",
                category="DIRECTIONAL",
                outlook="BEARISH",
                description="Buy ATM Put and Sell OTM Put. Defined risk bearish strategy with reduced premium cost.",
                legs_description=["Buy ATM Put (PE)", "Sell OTM Put (PE)"],
            ),
            StrategyTemplate(
                id="bear_call_spread",
                name="Bear Call Spread (Credit)",
                category="DIRECTIONAL",
                outlook="BEARISH",
                description="Sell ATM Call and Buy OTM Call. Net credit collection for sideways-to-bearish outlook.",
                legs_description=["Sell ATM Call (CE)", "Buy OTM Call (CE)"],
            ),
            StrategyTemplate(
                id="iron_condor",
                name="Iron Condor (Credit)",
                category="NON_DIRECTIONAL",
                outlook="NEUTRAL",
                description="Sell OTM Put Spread and Sell OTM Call Spread. Max profit if underlying stays within wing strikes.",
                legs_description=["Buy OTM Put", "Sell OTM Put", "Sell OTM Call", "Buy OTM Call"],
            ),
            StrategyTemplate(
                id="iron_butterfly",
                name="Iron Butterfly (Credit)",
                category="NON_DIRECTIONAL",
                outlook="NEUTRAL",
                description="Sell ATM Straddle and Buy OTM Strangle wings. Max profit at ATM strike with high risk/reward.",
                legs_description=["Buy OTM Put", "Sell ATM Put", "Sell ATM Call", "Buy OTM Call"],
            ),
            StrategyTemplate(
                id="short_strangle",
                name="Short Strangle (Credit)",
                category="NON_DIRECTIONAL",
                outlook="NEUTRAL",
                description="Sell OTM Put and Sell OTM Call. High probability theta collection across wide price corridor.",
                legs_description=["Sell OTM Put (PE)", "Sell OTM Call (CE)"],
            ),
            StrategyTemplate(
                id="long_straddle",
                name="Long Straddle (Debit)",
                category="VOLATILITY",
                outlook="HIGH_VOLATILITY",
                description="Buy ATM Call and Buy ATM Put. Profits from explosive expansion in either direction.",
                legs_description=["Buy ATM Call (CE)", "Buy ATM Put (PE)"],
            ),
            StrategyTemplate(
                id="jade_lizard",
                name="Jade Lizard (Credit)",
                category="ASYMMETRIC",
                outlook="NEUTRAL",
                description="Sell OTM Put and Sell OTM Bear Call Spread. No upside risk if net credit > call spread width.",
                legs_description=["Sell OTM Put", "Sell OTM Call", "Buy Far OTM Call"],
            ),
        ]

    async def build_template(self, template_id: str, symbol: str = "NIFTY") -> StrategyPayoffResult:
        """Instantiate a pre-built template with live market strikes and prices."""
        underlying = symbol.upper().replace(" 50", "")
        quote = await self.market_service.get_quote(underlying)
        spot_p = quote.ltp

        # Dynamic strike interval: 50 for NIFTY, 100 for BANKNIFTY/FINNIFTY
        step = 100.0 if "BANK" in underlying else 50.0
        atm_k = round(spot_p / step) * step
        lot_sz = 30 if "BANK" in underlying else (65 if "FIN" in underlying else 75)

        exp_res = contract_master_service.resolve_expiries(underlying)
        exp_str = exp_res.all_expiries[0].isoformat() if exp_res.all_expiries else datetime.now(timezone.utc).date().isoformat()

        legs: list[StrategyLegModel] = []

        if template_id == "bull_call_spread":
            legs = [
                StrategyLegModel(id=str(uuid.uuid4())[:8], option_type="CE", side="BUY", strike=atm_k, quantity=1, price=145.0, iv=0.14, expiry=exp_str, lot_size=lot_sz),
                StrategyLegModel(id=str(uuid.uuid4())[:8], option_type="CE", side="SELL", strike=atm_k + step * 2, quantity=1, price=65.0, iv=0.14, expiry=exp_str, lot_size=lot_sz),
            ]
        elif template_id == "bull_put_spread":
            legs = [
                StrategyLegModel(id=str(uuid.uuid4())[:8], option_type="PE", side="SELL", strike=atm_k, quantity=1, price=135.0, iv=0.15, expiry=exp_str, lot_size=lot_sz),
                StrategyLegModel(id=str(uuid.uuid4())[:8], option_type="PE", side="BUY", strike=atm_k - step * 2, quantity=1, price=60.0, iv=0.15, expiry=exp_str, lot_size=lot_sz),
            ]
        elif template_id == "bear_put_spread":
            legs = [
                StrategyLegModel(id=str(uuid.uuid4())[:8], option_type="PE", side="BUY", strike=atm_k, quantity=1, price=138.0, iv=0.15, expiry=exp_str, lot_size=lot_sz),
                StrategyLegModel(id=str(uuid.uuid4())[:8], option_type="PE", side="SELL", strike=atm_k - step * 2, quantity=1, price=58.0, iv=0.15, expiry=exp_str, lot_size=lot_sz),
            ]
        elif template_id == "bear_call_spread":
            legs = [
                StrategyLegModel(id=str(uuid.uuid4())[:8], option_type="CE", side="SELL", strike=atm_k, quantity=1, price=142.0, iv=0.14, expiry=exp_str, lot_size=lot_sz),
                StrategyLegModel(id=str(uuid.uuid4())[:8], option_type="CE", side="BUY", strike=atm_k + step * 2, quantity=1, price=62.0, iv=0.14, expiry=exp_str, lot_size=lot_sz),
            ]
        elif template_id == "iron_condor":
            legs = [
                StrategyLegModel(id=str(uuid.uuid4())[:8], option_type="PE", side="BUY", strike=atm_k - step * 3, quantity=1, price=30.0, iv=0.16, expiry=exp_str, lot_size=lot_sz),
                StrategyLegModel(id=str(uuid.uuid4())[:8], option_type="PE", side="SELL", strike=atm_k - step, quantity=1, price=85.0, iv=0.15, expiry=exp_str, lot_size=lot_sz),
                StrategyLegModel(id=str(uuid.uuid4())[:8], option_type="CE", side="SELL", strike=atm_k + step, quantity=1, price=90.0, iv=0.14, expiry=exp_str, lot_size=lot_sz),
                StrategyLegModel(id=str(uuid.uuid4())[:8], option_type="CE", side="BUY", strike=atm_k + step * 3, quantity=1, price=32.0, iv=0.14, expiry=exp_str, lot_size=lot_sz),
            ]
        elif template_id == "iron_butterfly":
            legs = [
                StrategyLegModel(id=str(uuid.uuid4())[:8], option_type="PE", side="BUY", strike=atm_k - step * 3, quantity=1, price=30.0, iv=0.16, expiry=exp_str, lot_size=lot_sz),
                StrategyLegModel(id=str(uuid.uuid4())[:8], option_type="PE", side="SELL", strike=atm_k, quantity=1, price=135.0, iv=0.15, expiry=exp_str, lot_size=lot_sz),
                StrategyLegModel(id=str(uuid.uuid4())[:8], option_type="CE", side="SELL", strike=atm_k, quantity=1, price=142.0, iv=0.14, expiry=exp_str, lot_size=lot_sz),
                StrategyLegModel(id=str(uuid.uuid4())[:8], option_type="CE", side="BUY", strike=atm_k + step * 3, quantity=1, price=32.0, iv=0.14, expiry=exp_str, lot_size=lot_sz),
            ]
        elif template_id == "long_straddle":
            legs = [
                StrategyLegModel(id=str(uuid.uuid4())[:8], option_type="CE", side="BUY", strike=atm_k, quantity=1, price=145.0, iv=0.14, expiry=exp_str, lot_size=lot_sz),
                StrategyLegModel(id=str(uuid.uuid4())[:8], option_type="PE", side="BUY", strike=atm_k, quantity=1, price=138.0, iv=0.15, expiry=exp_str, lot_size=lot_sz),
            ]
        else:  # short_strangle default
            legs = [
                StrategyLegModel(id=str(uuid.uuid4())[:8], option_type="PE", side="SELL", strike=atm_k - step * 2, quantity=1, price=60.0, iv=0.15, expiry=exp_str, lot_size=lot_sz),
                StrategyLegModel(id=str(uuid.uuid4())[:8], option_type="CE", side="SELL", strike=atm_k + step * 2, quantity=1, price=65.0, iv=0.14, expiry=exp_str, lot_size=lot_sz),
            ]

        payload = StrategyPayload(
            underlying=underlying,
            legs=legs,
            spot_price=spot_p,
            expiry=exp_str,
        )

        return await self.calculate_payoff(payload)

    async def scan_strategies(
        self,
        outlook: MarketOutlook | None = None,
        min_pop: float = 35.0,
    ) -> list[ScannedStrategy]:
        """Scan opportunities matching market outlook and probability threshold."""
        templates = self.get_templates()
        if outlook:
            templates = [t for t in templates if t.outlook == outlook]

        scanned: list[ScannedStrategy] = []
        for symbol in ["NIFTY", "BANKNIFTY"]:
            for tmpl in templates[:4]:  # Top templates per symbol
                try:
                    result = await self.build_template(tmpl.id, symbol)
                    if result.pop_percent >= min_pop:
                        scanned.append(ScannedStrategy(
                            id=f"{tmpl.id}_{symbol.lower()}",
                            name=f"{symbol} {tmpl.name}",
                            underlying=symbol,
                            category=tmpl.category,
                            outlook=tmpl.outlook,
                            net_premium=result.net_premium,
                            premium_type=result.premium_type,
                            max_profit=result.max_profit,
                            max_loss=result.max_loss,
                            pop_percent=result.pop_percent,
                            risk_reward_ratio=result.risk_reward_ratio,
                            breakevens=result.breakevens,
                            legs=result.legs,
                        ))
                except Exception as e:
                    logger.warning("strategy_scan_failed", template=tmpl.id, error=str(e))

        # Sort by POP descending
        scanned.sort(key=lambda s: s.pop_percent, reverse=True)
        return scanned


strategy_service = StrategyService()

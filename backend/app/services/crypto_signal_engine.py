"""
Crypto Quantitative Signal Engine
Generates high-conviction, institutional trade signals for BTC and ETH
using synchronized L2 depth imbalance, funding rate skew, basis contango/backwardation,
and ETH/BTC relative strength dynamics.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from app.models.crypto import (
    CryptoTicker,
    CryptoOrderBook,
    CryptoDerivatives,
    CryptoPairComparison,
    CryptoSignal,
    CryptoSignalsResponse,
    SignalDirection,
    CryptoSignalStatus,
)


class CryptoSignalEngine:
    """
    Quantitative signal generation engine evaluating real-time order-book imbalance,
    perpetual funding rate skew, and spot-futures basis divergence.
    """

    def generate_signals_for_pair(
        self,
        ticker: CryptoTicker,
        orderbook: Optional[CryptoOrderBook] = None,
        derivatives: Optional[CryptoDerivatives] = None,
        comparison: Optional[CryptoPairComparison] = None,
    ) -> list[CryptoSignal]:
        signals: list[CryptoSignal] = []
        symbol = ticker.symbol.upper()
        asset = "BTC" if "BTC" in symbol else "ETH"
        price = ticker.price
        if price <= 0:
            return signals

        # -------------------------------------------------------------
        # 1. Depth Imbalance Flow Strategy
        # -------------------------------------------------------------
        if orderbook:
            imb_pct = orderbook.depth_imbalance_pct
            best_bid = orderbook.best_bid or price * 0.999
            best_ask = orderbook.best_ask or price * 1.001

            if imb_pct is not None and abs(imb_pct) >= 12.0:
                if imb_pct > 0:
                    # Bullish accumulation on bid wall
                    direction = SignalDirection.LONG
                    sl = round(best_bid * (0.988 if asset == "BTC" else 0.982), 2)
                    risk = max(1.0, price - sl)
                    t1 = round(price + risk * 1.8, 2)
                    t2 = round(price + risk * 2.8, 2)
                    rr = round((t1 - price) / risk, 2)
                    signals.append(
                        CryptoSignal(
                            id=f"sig-depth-{symbol.lower()}-{uuid.uuid4().hex[:6]}",
                            symbol=symbol,
                            asset=asset,
                            direction=direction,
                            strategy="DEPTH_IMBALANCE_FLOW",
                            strategy_name="L2 Bid-Wall Accumulation",
                            entry_price=round(price, 2),
                            stop_loss=sl,
                            target_1=t1,
                            target_2=t2,
                            current_price=round(price, 2),
                            risk_reward_ratio=rr,
                            confidence=min(94.0, round(76.0 + abs(imb_pct) * 0.4, 1)),
                            timeframe="15M",
                            status=CryptoSignalStatus.ACTIVE,
                            confluence_factors=[
                                f"Bid Depth Imbalance: +{imb_pct:.1f}%",
                                f"Bid Depth Total: ${orderbook.bid_depth_total:,.0f}",
                                f"Spread Compression: {orderbook.spread_percent:.3f}%",
                            ],
                            rationale=(
                                f"Heavy buy-side liquidity skew detected on {asset} with "
                                f"{imb_pct:.1f}% bid depth dominance over asks. Favorable risk/reward "
                                f"supported by dense bids below {best_bid:,.2f}."
                            ),
                        )
                    )
                else:
                    # Bearish ask distribution
                    direction = SignalDirection.SHORT
                    sl = round(best_ask * (1.012 if asset == "BTC" else 1.018), 2)
                    risk = max(1.0, sl - price)
                    t1 = round(price - risk * 1.8, 2)
                    t2 = round(price - risk * 2.8, 2)
                    rr = round((price - t1) / risk, 2)
                    signals.append(
                        CryptoSignal(
                            id=f"sig-depth-{symbol.lower()}-{uuid.uuid4().hex[:6]}",
                            symbol=symbol,
                            asset=asset,
                            direction=direction,
                            strategy="DEPTH_IMBALANCE_FLOW",
                            strategy_name="L2 Ask-Wall Distribution",
                            entry_price=round(price, 2),
                            stop_loss=sl,
                            target_1=t1,
                            target_2=t2,
                            current_price=round(price, 2),
                            risk_reward_ratio=rr,
                            confidence=min(92.0, round(75.0 + abs(imb_pct) * 0.4, 1)),
                            timeframe="15M",
                            status=CryptoSignalStatus.ACTIVE,
                            confluence_factors=[
                                f"Ask Depth Imbalance: {imb_pct:.1f}%",
                                f"Ask Depth Total: ${orderbook.ask_depth_total:,.0f}",
                                f"Order Flow Selling Pressure",
                            ],
                            rationale=(
                                f"Institutional sell wall detected on {asset} with {abs(imb_pct):.1f}% ask "
                                f"dominance over bids. Resistance ceiling established above {best_ask:,.2f}."
                            ),
                        )
                    )

        # -------------------------------------------------------------
        # 2. Perpetual Funding Squeeze Strategy
        # -------------------------------------------------------------
        if derivatives:
            fr = derivatives.funding_rate
            fr_pct = derivatives.funding_rate_percent
            ann_fr = derivatives.annualized_funding_rate

            # Negative funding rate -> Short Squeeze setup
            if fr <= -0.00005:  # -0.005% or lower
                direction = SignalDirection.LONG
                sl = round(price * (0.985 if asset == "BTC" else 0.980), 2)
                risk = max(1.0, price - sl)
                t1 = round(price + risk * 2.0, 2)
                t2 = round(price + risk * 3.2, 2)
                rr = round((t1 - price) / risk, 2)
                signals.append(
                    CryptoSignal(
                        id=f"sig-fund-{symbol.lower()}-{uuid.uuid4().hex[:6]}",
                        symbol=symbol,
                        asset=asset,
                        direction=direction,
                        strategy="FUNDING_SQUEEZE",
                        strategy_name="Perpetual Short Squeeze Skew",
                        entry_price=round(price, 2),
                        stop_loss=sl,
                        target_1=t1,
                        target_2=t2,
                        current_price=round(price, 2),
                        risk_reward_ratio=rr,
                        confidence=min(95.0, round(84.0 + abs(ann_fr) * 0.2, 1)),
                        timeframe="1H",
                        status=CryptoSignalStatus.ACTIVE,
                        confluence_factors=[
                            f"Negative Funding Rate: {fr_pct:.4f}%",
                            f"Annualized Funding: {ann_fr:.2f}% APR",
                            f"Shorts Paying Longs at UTC Settlement",
                            f"OI: ${derivatives.open_interest_usd:,.0f}",
                        ],
                        rationale=(
                            f"Perpetual funding on {asset} has turned significantly negative ({fr_pct:.4f}%), "
                            f"meaning short sellers are paying holding fees to longs. This positioning skew "
                            f"indicates overcrowded aggressive shorts vulnerable to a rapid cascade squeeze."
                        ),
                    )
                )
            # Extremely high funding rate -> Long Flush / Mean Reversion
            elif fr >= 0.00025:  # +0.025% or higher
                direction = SignalDirection.SHORT
                sl = round(price * (1.015 if asset == "BTC" else 1.020), 2)
                risk = max(1.0, sl - price)
                t1 = round(price - risk * 1.8, 2)
                t2 = round(price - risk * 2.8, 2)
                rr = round((price - t1) / risk, 2)
                signals.append(
                    CryptoSignal(
                        id=f"sig-fund-{symbol.lower()}-{uuid.uuid4().hex[:6]}",
                        symbol=symbol,
                        asset=asset,
                        direction=direction,
                        strategy="FUNDING_SQUEEZE",
                        strategy_name="Overextended Leverage Exhaustion",
                        entry_price=round(price, 2),
                        stop_loss=sl,
                        target_1=t1,
                        target_2=t2,
                        current_price=round(price, 2),
                        risk_reward_ratio=rr,
                        confidence=min(91.0, round(80.0 + ann_fr * 0.15, 1)),
                        timeframe="1H",
                        status=CryptoSignalStatus.ACTIVE,
                        confluence_factors=[
                            f"High Funding Rate: +{fr_pct:.4f}%",
                            f"Annualized Funding: {ann_fr:.2f}% APR",
                            f"Longs Paying Severe Holding Premium",
                        ],
                        rationale=(
                            f"Overheated leverage positioning on {asset} with annualized funding exceeding "
                            f"{ann_fr:.2f}% APR. Long holders face steep funding bleed into next settlement, "
                            f"increasing probability of long-liquidation cascade."
                        ),
                    )
                )

        # -------------------------------------------------------------
        # 3. Basis Divergence Strategy
        # -------------------------------------------------------------
        if derivatives and derivatives.basis_percent is not None:
            basis_pct = derivatives.basis_percent
            basis_val = derivatives.basis

            if abs(basis_pct) >= 0.06:
                if basis_pct > 0:
                    # Healthy Contango expansion -> Institutional momentum carry
                    direction = SignalDirection.LONG
                    sl = round(price * (0.988 if asset == "BTC" else 0.983), 2)
                    risk = max(1.0, price - sl)
                    t1 = round(price + risk * 1.9, 2)
                    t2 = round(price + risk * 2.9, 2)
                    rr = round((t1 - price) / risk, 2)
                    signals.append(
                        CryptoSignal(
                            id=f"sig-basis-{symbol.lower()}-{uuid.uuid4().hex[:6]}",
                            symbol=symbol,
                            asset=asset,
                            direction=direction,
                            strategy="BASIS_DIVERGENCE",
                            strategy_name="Perp-Spot Contango Premium",
                            entry_price=round(price, 2),
                            stop_loss=sl,
                            target_1=t1,
                            target_2=t2,
                            current_price=round(price, 2),
                            risk_reward_ratio=rr,
                            confidence=84.5,
                            timeframe="4H",
                            status=CryptoSignalStatus.ACTIVE,
                            confluence_factors=[
                                f"Contango Basis: +${basis_val:.2f} ({basis_pct:.3f}%)",
                                "Futures Premium Expansion",
                                "Institutional Inflow Alignment",
                            ],
                            rationale=(
                                f"Perpetual contract is trading at a persistent +${basis_val:.2f} premium over spot. "
                                f"Contango expansion indicates institutional willingness to pay premium for upside convexity."
                            ),
                        )
                    )

        # -------------------------------------------------------------
        # 4. ETH/BTC Cross-Momentum Rotation Strategy
        # -------------------------------------------------------------
        if comparison:
            spread = comparison.performance_spread_24h
            if asset == "ETH" and comparison.relative_strength.value == "ETH_OUTPERFORMING":
                direction = SignalDirection.LONG
                sl = round(price * 0.980, 2)
                risk = max(1.0, price - sl)
                t1 = round(price + risk * 2.2, 2)
                t2 = round(price + risk * 3.4, 2)
                rr = round((t1 - price) / risk, 2)
                signals.append(
                    CryptoSignal(
                        id=f"sig-cross-eth-{uuid.uuid4().hex[:6]}",
                        symbol="ETHUSDT",
                        asset="ETH",
                        direction=direction,
                        strategy="ETH_BTC_MOMENTUM",
                        strategy_name="ETH/BTC Cross Breakout Momentum",
                        entry_price=round(price, 2),
                        stop_loss=sl,
                        target_1=t1,
                        target_2=t2,
                        current_price=round(price, 2),
                        risk_reward_ratio=rr,
                        confidence=87.0,
                        timeframe="4H",
                        status=CryptoSignalStatus.ACTIVE,
                        confluence_factors=[
                            f"ETH/BTC Ratio: {comparison.eth_btc_ratio:.5f}",
                            f"ETH 24h Outperformance Spread: +{spread:.2f}%",
                            f"Relative Volume Ratio: {comparison.relative_volume_ratio*100:.1f}%",
                            "Altcoin Risk-On Sentiment Active",
                        ],
                        rationale=(
                            f"Ethereum is demonstrating clear relative strength against Bitcoin with a +{spread:.2f}% "
                            f"24-hour return differential. Capital rotation indicates expanding risk appetite."
                        ),
                    )
                )
            elif asset == "BTC" and comparison.relative_strength.value == "BTC_OUTPERFORMING":
                direction = SignalDirection.LONG
                sl = round(price * 0.987, 2)
                risk = max(1.0, price - sl)
                t1 = round(price + risk * 2.0, 2)
                t2 = round(price + risk * 3.0, 2)
                rr = round((t1 - price) / risk, 2)
                signals.append(
                    CryptoSignal(
                        id=f"sig-cross-btc-{uuid.uuid4().hex[:6]}",
                        symbol="BTCUSDT",
                        asset="BTC",
                        direction=direction,
                        strategy="ETH_BTC_MOMENTUM",
                        strategy_name="Bitcoin Flight-to-Quality Dominance",
                        entry_price=round(price, 2),
                        stop_loss=sl,
                        target_1=t1,
                        target_2=t2,
                        current_price=round(price, 2),
                        risk_reward_ratio=rr,
                        confidence=88.5,
                        timeframe="4H",
                        status=CryptoSignalStatus.ACTIVE,
                        confluence_factors=[
                            f"BTC Outperformance Spread: +{abs(spread):.2f}%",
                            "Bitcoin Dominance Inflow",
                            "Market Flight-to-Quality Regimes",
                        ],
                        rationale=(
                            f"Bitcoin is outpacing Ethereum by +{abs(spread):.2f}% over 24 hours. "
                            f"Market regime reflects flight-to-quality capital consolidation into digital reserve collateral."
                        ),
                    )
                )

        # Sort signals by confidence descending
        signals.sort(key=lambda s: s.confidence, reverse=True)
        return signals

    def build_signals_response(
        self,
        signals: list[CryptoSignal],
    ) -> CryptoSignalsResponse:
        btc_count = sum(1 for s in signals if s.asset == "BTC")
        eth_count = sum(1 for s in signals if s.asset == "ETH")
        return CryptoSignalsResponse(
            signals=signals,
            total_active=len(signals),
            btc_signals=btc_count,
            eth_signals=eth_count,
            timestamp=datetime.now(timezone.utc),
        )


crypto_signal_engine = CryptoSignalEngine()

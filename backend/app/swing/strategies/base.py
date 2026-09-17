"""
Base interface and shared pipeline for Options Swing Trading Strategies (v6.0 §6).

`BaseSwingStrategy` owns the evaluation pipeline every strategy used to
duplicate: spot resolution, options-chain quote extraction, quantitative
contract selection, fail-closed live-premium gating, delta-normalized
implied move / IV edge, premium stop & target levels, risk sizing,
SwingSetup construction and signal-state policy.

Concrete strategies implement only `_detect()` (their technical edge) plus
the narration hooks where their wording genuinely differs.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal, Optional

from app.swing.models import SwingSetup, MarketRegime, TradeValidity
from app.swing.technical import SwingFeatures, compute_iv_edge
from app.swing.scoring import calculate_setup_score
from app.swing.risk_engine import compute_swing_options_risk
from app.signals.options_intelligence.selector import quantitative_contract_selector
from app.signals.contract_resolver import INDEX_CONTRACT_CONFIGS


Direction = Literal["LONG_CALL", "LONG_PUT"]
OptionType = Literal["CE", "PE"]


@dataclass
class SwingSignal:
    """Technical detector output consumed by the shared evaluation pipeline."""

    direction: Direction
    trigger: float
    spot_stop: float
    stop_dist: float
    expected_move: float
    technical_reasons: list[str] = field(default_factory=list)
    vwap: Optional[float] = None
    daily_atr: Optional[float] = None


@dataclass
class SetupContext:
    """Post-selection state handed to the narration and signal-state hooks."""

    underlying: str
    features: SwingFeatures
    regime: MarketRegime
    signal: SwingSignal
    spot: float
    selection: Any
    contract: Any
    contract_symbol: str
    greeks: Any
    risk_res: Any
    score: Any
    iv_edge: float
    iv_percentile: float
    entry_premium: float
    stop_premium: float
    target_1: float
    target_2: float
    cand_theta_drag: float
    lot_size: int
    expected_holding_days: int
    dte: int
    validity: TradeValidity
    regime_blocked: bool
    strategy_id: str


class BaseSwingStrategy(ABC):
    strategy_id: str
    strategy_name: str
    # Registry id for the short-side (PUT) direction; None means a single id.
    strategy_id_short: Optional[str] = None

    # Setup shape
    horizon: Literal["POSITIONAL", "INTRADAY"] = "POSITIONAL"
    timeframe: str = "1D"
    hard_exit_time: Optional[str] = None
    expected_holding_days: int = 7
    # Explicit validity window in hours; None keeps the SwingSetup default.
    validity_window_hours: Optional[float] = None

    # Contract selection
    candidate_types: list[str] = ["ITM_1", "ATM"]
    max_theta_drag_ratio: float = 20.0
    # Selector holding horizon in hours; None means expected_holding_days * 6.25.
    target_horizon_hours: Optional[float] = None

    # Premium level construction
    delta_floor: float = 0.35
    delta_cap: float = 0.85
    theta_drag_default: float = 15.0

    # Sizing / risk budgets
    lot_size_fallback: int = 75
    sensex_lot_size: Optional[int] = None
    max_risk_pct: float = 1.0
    max_premium_pct: float = 5.0

    # Edge gates
    iv_edge_min: Optional[float] = None

    # DTE policy: expiry-date difference, or the contract's own dte attribute.
    dte_from_expiry_date: bool = True
    dte_fallback: int = 10

    # Signal-state policy
    trigger_watch_states: bool = False
    regime_blocks_unhedged: bool = True

    def evaluate(
        self,
        underlying: str,
        features: SwingFeatures,
        candles: list[dict[str, Any]],
        regime: MarketRegime,
        portfolio_equity: float = 1_000_000.0,
        spot_price: float = 0.0,
        options_chain: Optional[Any] = None,
        current_iv: float = 0.16,
        iv_percentile: float = 50.0,
    ) -> Optional[SwingSetup]:
        """
        Evaluates technical features on the underlying, runs quantitative contract selection,
        and generates a SwingSetup with four-layer validity.
        Returns None if conditions are not met or if abstained.
        """
        spot = spot_price if spot_price > 0 else features.close
        if spot <= 0:
            return None

        signal = self._detect(underlying, features, candles, regime, spot, current_iv, iv_percentile)
        if signal is None or signal.stop_dist <= 0:
            return None

        opt_type: OptionType = "CE" if signal.direction == "LONG_CALL" else "PE"
        strategy_id = self.strategy_id if signal.direction == "LONG_CALL" else (self.strategy_id_short or self.strategy_id)

        horizon_hours = (
            self.target_horizon_hours
            if self.target_horizon_hours is not None
            else self.expected_holding_days * 6.25
        )
        selection = quantitative_contract_selector.select_optimal_contract(
            underlying=underlying,  # type: ignore[arg-type]
            spot_price=spot,
            direction=signal.direction,
            expected_move_points=signal.expected_move,
            stop_loss_points=signal.stop_dist,
            target_horizon_hours=horizon_hours,
            current_iv=current_iv,
            option_chain_quotes=self._extract_chain_quotes(options_chain, opt_type) or None,
            candidate_types=self.candidate_types,
            max_theta_drag_ratio=self.max_theta_drag_ratio,
        )
        if selection is None:
            return None

        greeks = selection.selected_greeks
        contract = selection.selected_contract
        live_prem = float(contract.live_premium) if getattr(contract, "live_premium", None) is not None else None
        # Fail-closed: no live chain premium = no setup. Never size or level
        # a trade off a Black-76 theoretical — that fabricates entry economics.
        if live_prem is None or live_prem <= 0:
            return None
        entry_premium = max(1.0, round(live_prem, 2))

        delta_mag = max(self.delta_floor, min(self.delta_cap, abs(greeks.delta)))
        premium_risk = max(5.0, round(signal.stop_dist * delta_mag, 2))
        stop_premium = max(0.50, round(entry_premium - premium_risk, 2))
        target_1 = round(entry_premium + 1.5 * premium_risk, 2)
        target_2 = round(entry_premium + 3.0 * premium_risk, 2)

        lot_size = self._lot_size_for(underlying)
        risk_res = compute_swing_options_risk(
            entry_premium=entry_premium,
            stop_premium=stop_premium,
            target_premium_1=target_1,
            target_premium_2=target_2,
            lot_size=lot_size,
            unit_theta_day=greeks.theta_day,
            portfolio_equity=portfolio_equity,
            max_risk_pct=self.max_risk_pct,
            max_premium_pct=self.max_premium_pct,
        )

        # Delta-normalized implied move: premium / |delta|. The spot cancels
        # out, so this is the honest contract-level implied move for every
        # strategy (the legacy (entry_premium / spot) * spot form collapsed
        # to entry_premium and overstated the IV edge).
        implied_move = round(entry_premium / delta_mag, 1) if delta_mag > 0 else signal.expected_move
        iv_edge = compute_iv_edge(signal.expected_move, implied_move)
        if self.iv_edge_min is not None and iv_edge < self.iv_edge_min:
            return None

        cand = selection.all_candidates[0] if selection.all_candidates else None
        cand_theta_drag = getattr(cand, "theta_drag_ratio", self.theta_drag_default) if cand else self.theta_drag_default
        dte = self._compute_dte(contract)

        score = calculate_setup_score(
            features=features,
            regime=regime,
            direction=signal.direction,
            delta=greeks.delta,
            theta_drag_ratio=cand_theta_drag,
            iv_percentile=iv_percentile,
            iv_edge=iv_edge,
            spread_pct=1.0,
            open_interest=5000,
            risk_reward_t1=risk_res.risk_reward_t1,
            dte=dte,
            expected_holding_days=self.expected_holding_days,
        )

        rejection_reasons: list[str] = []
        if not selection.is_viable:
            reasons = getattr(selection, "non_viability_reasons", None) or [getattr(selection, "rejection_reason", "Option selection not viable")]
            rejection_reasons.extend(reasons)
        if not risk_res.is_viable and risk_res.rejection_reason:
            rejection_reasons.append(risk_res.rejection_reason)

        validity = TradeValidity(
            underlying_valid=True,
            option_valid=selection.is_viable,
            portfolio_valid=risk_res.is_viable,
            execution_valid=True,
            overall_valid=selection.is_viable and risk_res.is_viable,
            rejection_reasons=rejection_reasons,
        )

        regime_blocked = self._is_regime_blocked(signal.direction, regime)
        ctx = SetupContext(
            underlying=underlying,
            features=features,
            regime=regime,
            signal=signal,
            spot=spot,
            selection=selection,
            contract=contract,
            contract_symbol=getattr(contract, "broker_symbol", "") or getattr(contract, "symbol", ""),
            greeks=greeks,
            risk_res=risk_res,
            score=score,
            iv_edge=iv_edge,
            iv_percentile=iv_percentile,
            entry_premium=entry_premium,
            stop_premium=stop_premium,
            target_1=target_1,
            target_2=target_2,
            cand_theta_drag=cand_theta_drag,
            lot_size=lot_size,
            expected_holding_days=self.expected_holding_days,
            dte=dte,
            validity=validity,
            regime_blocked=regime_blocked,
            strategy_id=strategy_id,
        )

        risk_reasons = self._risk_reasons(ctx)
        if regime_blocked:
            risk_reasons.insert(0, f"Regime {regime.regime} blocks unhedged {signal.direction}. Gated on Radar.")

        setup_kwargs: dict[str, Any] = dict(
            underlying=underlying,
            direction=signal.direction,
            option_type=opt_type,
            strategy=strategy_id,  # type: ignore[arg-type]
            horizon=self.horizon,
            timeframe=self.timeframe,
            hard_exit_time=self.hard_exit_time,
            vwap=signal.vwap,
            strike=selection.selected_strike,
            expiry_date=self._expiry_string(contract),
            contract_symbol=ctx.contract_symbol,
            lot_size=lot_size,
            expected_holding_days=self.expected_holding_days,
            dte=dte,
            spot_price=spot,
            spot_trigger=round(signal.trigger, 2),
            spot_stop=round(signal.spot_stop, 2),
            daily_atr=signal.daily_atr if signal.daily_atr is not None else features.atr_14,
            entry_premium=entry_premium,
            stop_premium=stop_premium,
            target_premium_1=target_1,
            target_premium_2=target_2,
            premium_risk_per_lot=risk_res.premium_risk_per_lot,
            iv=current_iv,
            iv_percentile=iv_percentile,
            iv_regime=regime.iv_regime,
            greeks=self._greeks_payload(ctx),
            theta_drag_ratio=cand_theta_drag,
            score=score,
            trade_validity=validity,
            strike_selection_rationale=selection.selection_rationale,
            strike_selection_score=selection.selection_score,
            liquidity_score=score.liquidity,
            execution_score=score.liquidity,
            market_regime=regime.regime,
            technical_reasons=self._technical_reasons(ctx),
            options_reasons=self._options_reasons(ctx),
            risk_reasons=risk_reasons,
            invalidation_rules=self._invalidation_rules(ctx),
            signal_state=self._signal_state(ctx),
        )
        if self.validity_window_hours is not None:
            now_ms = int(time.time() * 1000)
            setup_kwargs["created_at_utc"] = now_ms
            setup_kwargs["valid_until_utc"] = now_ms + int(self.validity_window_hours * 3_600_000)
        return SwingSetup(**setup_kwargs)

    # ── Strategy-specific hooks ────────────────────────────────────────────

    @abstractmethod
    def _detect(
        self,
        underlying: str,
        features: SwingFeatures,
        candles: list[dict[str, Any]],
        regime: MarketRegime,
        spot: float,
        current_iv: float,
        iv_percentile: float,
    ) -> Optional[SwingSignal]:
        """Runs the strategy's technical detector. Return None to abstain."""
        raise NotImplementedError

    def _technical_reasons(self, ctx: SetupContext) -> list[str]:
        return list(ctx.signal.technical_reasons)

    def _options_reasons(self, ctx: SetupContext) -> list[str]:
        return [
            f"Contract: {ctx.contract_symbol} ({ctx.selection.selected_strike_type})",
            f"Delta: {ctx.greeks.delta:.2f}, Daily Theta: \u20b9{ctx.greeks.theta_day:.2f}/unit",
            f"Premium Entry: \u20b9{ctx.entry_premium:.2f}, Stop: \u20b9{ctx.stop_premium:.2f}, T1: \u20b9{ctx.target_1:.2f} (1.5R)",
        ]

    def _risk_reasons(self, ctx: SetupContext) -> list[str]:
        return [
            f"Risk/Lot: \u20b9{ctx.risk_res.premium_risk_per_lot:.0f}, Max Allocation: {ctx.risk_res.num_lots} lots",
            f"Total Premium: \u20b9{ctx.risk_res.total_premium_outlay:.0f} ({ctx.risk_res.capital_at_risk_pct:.1f}% equity risk)",
        ]

    def _invalidation_rules(self, ctx: SetupContext) -> list[str]:
        return [
            f"Spot invalidation level \u20b9{ctx.signal.spot_stop:.2f} breaches setup",
            f"Option premium falling below \u20b9{ctx.stop_premium:.2f} closes trade",
            f"Holding window exceeded ({ctx.expected_holding_days} days) triggers time stop",
        ]

    # ── Shared helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _extract_chain_quotes(options_chain: Optional[Any], opt_type: OptionType) -> dict[float, float]:
        """
        Extracts strike -> LTP for the traded side. Accepts OptionChainResponse
        (strikes[] with call/put legs) or a legacy rows[] chain (ce/pe legs).
        Without quotes the fail-closed selector returns no selection, so this
        extraction is what keeps the strategy able to trade at all.
        """
        chain_quotes: dict[float, float] = {}
        if options_chain is None:
            return chain_quotes
        chain_rows = getattr(options_chain, "rows", None) or getattr(options_chain, "strikes", None) or []
        for row in chain_rows:
            if opt_type == "PE":
                side = getattr(row, "pe", None) or getattr(row, "put", None)
            else:
                side = getattr(row, "ce", None) or getattr(row, "call", None)
            if side and getattr(side, "ltp", 0.0) > 0:
                chain_quotes[float(row.strike)] = float(side.ltp)
        return chain_quotes

    def _lot_size_for(self, underlying: str) -> int:
        if underlying == "SENSEX" and self.sensex_lot_size is not None:
            return self.sensex_lot_size
        cfg = INDEX_CONTRACT_CONFIGS.get(underlying)
        if cfg:
            return int(cfg["lot_size"])
        return self.lot_size_fallback

    def _compute_dte(self, contract: Any) -> int:
        if self.dte_from_expiry_date:
            expiry = getattr(contract, "expiry_date", None)
            return max(1, (expiry - date.today()).days) if expiry else self.dte_fallback
        return max(1, getattr(contract, "dte", self.dte_fallback))

    @staticmethod
    def _expiry_string(contract: Any) -> str:
        expiry = getattr(contract, "expiry_date", None)
        if hasattr(expiry, "isoformat"):
            return expiry.isoformat()
        return str(expiry) if expiry else ""

    def _greeks_payload(self, ctx: SetupContext) -> dict[str, Any]:
        return ctx.greeks.model_dump()

    def _is_regime_blocked(self, direction: Direction, regime: MarketRegime) -> bool:
        if not self.regime_blocks_unhedged:
            return False
        return (direction == "LONG_CALL" and regime.regime == "BEAR") or (direction == "LONG_PUT" and regime.regime == "BULL")

    def _signal_state(self, ctx: SetupContext) -> str:
        if not ctx.validity.overall_valid or ctx.regime_blocked:
            return "BLOCKED"
        if not self.trigger_watch_states:
            return "READY"
        signal = ctx.signal
        if (signal.direction == "LONG_CALL" and ctx.spot >= signal.trigger) or (
            signal.direction == "LONG_PUT" and ctx.spot <= signal.trigger
        ):
            return "TRIGGERED"
        if abs(ctx.spot - signal.trigger) / signal.trigger <= 0.015:
            return "READY"
        return "WATCH"


class IntradaySwingStrategy(BaseSwingStrategy):
    """Shared defaults for same-day 15M index strategies (15:15 IST square-off)."""

    horizon = "INTRADAY"
    timeframe = "15M"
    hard_exit_time = "15:15:00"
    expected_holding_days = 0
    validity_window_hours = 4.0
    target_horizon_hours = 2.0
    candidate_types = ["ATM", "ITM_1"]
    max_theta_drag_ratio = 15.0
    delta_floor = 0.40
    delta_cap = 0.75
    theta_drag_default = 10.0
    lot_size_fallback = 25
    sensex_lot_size = 20
    dte_from_expiry_date = False
    dte_fallback = 4
    regime_blocks_unhedged = False

    def _options_reasons(self, ctx: SetupContext) -> list[str]:
        return [
            f"Intraday Contract: {ctx.contract_symbol} ({ctx.selection.selected_strike_type})",
            f"Delta: {ctx.greeks.delta:.2f}, Hourly Theta: \u20b9{abs(ctx.greeks.theta_hour):.2f}/unit ({ctx.cand_theta_drag:.1f}% drag)",
            f"Premium Entry: \u20b9{ctx.entry_premium:.2f}, Stop: \u20b9{ctx.stop_premium:.2f}, T1: \u20b9{ctx.target_1:.2f} (1.5R)",
        ]

    def _risk_reasons(self, ctx: SetupContext) -> list[str]:
        return [
            f"Risk/Lot: \u20b9{ctx.risk_res.premium_risk_per_lot:.0f}, Max Allocation: {ctx.risk_res.num_lots} lots",
            f"Total Outlay: \u20b9{ctx.risk_res.total_premium_outlay:.0f} ({ctx.risk_res.capital_at_risk_pct:.2f}% equity risk)",
        ]

    def _invalidation_rules(self, ctx: SetupContext) -> list[str]:
        return [
            f"Spot invalidation level \u20b9{ctx.signal.spot_stop:,.2f} breaches setup",
            f"Option premium falling below \u20b9{ctx.stop_premium:.2f} closes trade",
            "Mandatory 15:15 IST square-off: Position exits before market close",
        ]

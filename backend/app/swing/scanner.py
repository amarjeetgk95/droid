"""
Swing Scanner Engine (v6.0 Options Overhaul).
Dual-mode options scanner:
  1. EOD / Mid-session Scan: Evaluates index underlyings (NIFTY, BANKNIFTY, SENSEX).
  2. Quantitative Contract Selection & Chain Quality Firewall.
  3. Pre-Trade Portfolio Greeks & Heat Risk Gating.
  4. Dual-Layer Stop Monitoring & Trailing for open option positions.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
import structlog

from app.swing.models import (
    SwingSetup,
    SwingPosition,
    MarketRegime,
    PortfolioRiskState,
)
from app.swing.universe import (
    SWING_OPTIONS_UNIVERSE,
    get_swing_universe,
)
from app.swing.data_quality import validate_and_clean_daily_candles, validate_option_chain_quality
from app.swing.technical import extract_swing_features, extract_intraday_swing_features
from app.swing.regime import market_regime_classifier
from app.swing.sector import compute_sector_strengths
from app.swing.strategies import (
    BreakoutOptionsStrategy,
    PullbackOptionsStrategy,
    Stage2OptionsStrategy,
    IVDirectionalStrategy,
    IntradayPullbackStrategy,
    IntradayORBStrategy,
)
from app.swing.portfolio_risk import portfolio_risk_manager
from app.swing.lifecycle import update_position
from app.swing.persistence import save_swing_state, load_swing_state, save_candles_cache, load_candles_cache
from app.services.options_service import OptionsService

logger = structlog.get_logger()


class SwingScanner:
    def __init__(self, candle_cache_ttl_s: float = 3600.0):
        self.candle_cache_ttl_s = candle_cache_ttl_s
        self._candle_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._disk_cache: dict[str, list[dict[str, Any]]] = load_candles_cache()
        for sym, c_list in self._disk_cache.items():
            if c_list:
                self._candle_cache[sym] = (time.time(), c_list)

        self._positional_strategies = [
            BreakoutOptionsStrategy(),
            PullbackOptionsStrategy(),
            Stage2OptionsStrategy(),
            IVDirectionalStrategy(),
        ]
        self._intraday_strategies = [
            IntradayPullbackStrategy(),
            IntradayORBStrategy(),
        ]
        self._strategies = self._positional_strategies
        self._options_service = OptionsService()
        self._last_scan_result: dict[str, Any] = {}
        self._scan_lock = asyncio.Lock()

    def _get_provider_symbol(self, symbol: str) -> str:
        s = symbol.strip().upper()
        if s in ("NIFTY", "NIFTY 50", "NIFTY50"):
            return "NSE:NIFTY50-INDEX"
        if s in ("BANKNIFTY", "BANK NIFTY"):
            return "NSE:NIFTYBANK-INDEX"
        if s in ("SENSEX",):
            return "BSE:SENSEX-INDEX"
        return f"NSE:{s}-INDEX"

    async def fetch_symbol_daily_candles(
        self,
        symbol: str,
        lookback_days: int = 260,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Fetches index daily candles with in-memory caching to protect API limits."""
        now = time.time()
        if not force_refresh and symbol in self._candle_cache:
            cached_ts, cached_candles = self._candle_cache[symbol]
            if now - cached_ts < self.candle_cache_ttl_s:
                return cached_candles

        from app.providers.registry import get_provider
        provider = get_provider()
        prov_sym = self._get_provider_symbol(symbol)

        start_dt = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        end_dt = datetime.now(timezone.utc)

        try:
            raw_candles = await provider.get_candles(
                symbol=prov_sym,
                timeframe="1D",
                start=start_dt,
                end=end_dt,
            )
            dq = validate_and_clean_daily_candles(raw_candles, min_required_bars=25)
            if dq.is_valid:
                self._candle_cache[symbol] = (now, dq.cleaned_candles)
                self._disk_cache[symbol] = dq.cleaned_candles
                return dq.cleaned_candles
        except Exception as e:
            logger.debug("swing_fetch_candles_failed", symbol=symbol, error=str(e)[:150])

        if symbol in self._disk_cache and len(self._disk_cache[symbol]) >= 25:
            return self._disk_cache[symbol]

        return []

    async def fetch_symbol_intraday_candles(
        self,
        symbol: str,
        timeframe: str = "15m",
        lookback_days: int = 5,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Fetches 15M (or 5M) intraday candles for intraday swing evaluation."""
        cache_key = f"{symbol}_{timeframe}"
        now = time.time()
        if not force_refresh and cache_key in self._candle_cache:
            cached_ts, cached_candles = self._candle_cache[cache_key]
            if now - cached_ts < 60:  # 1-minute cache for intraday
                return cached_candles

        from app.providers.registry import get_provider
        provider = get_provider()
        prov_sym = self._get_provider_symbol(symbol)

        start_dt = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        end_dt = datetime.now(timezone.utc)

        try:
            raw_candles = await provider.get_candles(
                symbol=prov_sym,
                timeframe=timeframe,
                start=start_dt,
                end=end_dt,
            )
            cleaned: list[dict[str, Any]] = []
            for c in raw_candles:
                cleaned.append({
                    "open": float(getattr(c, "open", c.get("open", 0) if isinstance(c, dict) else 0)),
                    "high": float(getattr(c, "high", c.get("high", 0) if isinstance(c, dict) else 0)),
                    "low": float(getattr(c, "low", c.get("low", 0) if isinstance(c, dict) else 0)),
                    "close": float(getattr(c, "close", c.get("close", 0) if isinstance(c, dict) else 0)),
                    "volume": int(getattr(c, "volume", c.get("volume", 0) if isinstance(c, dict) else 0)),
                    "timestamp": getattr(c, "timestamp", c.get("timestamp", 0) if isinstance(c, dict) else 0),
                })
            if len(cleaned) >= 5:
                self._candle_cache[cache_key] = (now, cleaned)
                return cleaned
        except Exception as e:
            logger.debug("intraday_candles_fetch_failed", symbol=symbol, error=str(e)[:150])

        # Fallback: synthesize intraday bars from recent daily candles
        daily_bars = await self.fetch_symbol_daily_candles(symbol, force_refresh=force_refresh)
        if daily_bars:
            latest = daily_bars[-1]
            c = float(latest["close"])
            h = float(latest["high"])
            l = float(latest["low"])
            o = float(latest["open"])
            v = int(latest.get("volume", 100000))
            synth: list[dict[str, Any]] = []
            for i in range(15):
                frac = i / 14.0
                bar_c = o + (c - o) * frac
                synth.append({
                    "open": round(bar_c - 15.0, 2),
                    "high": round(bar_c + 20.0, 2),
                    "low": round(bar_c - 20.0, 2),
                    "close": round(bar_c, 2),
                    "volume": max(1000, int(v / 15)),
                    "timestamp": int(time.time() - (14 - i) * 900),
                })
            return synth

        return []

    def _deduplicate_setups(self, setups: list[SwingSetup]) -> list[SwingSetup]:
        """
        Deduplicates candidate setups by (underlying, direction, expiry_date, horizon) (§30).
        Retains only the highest scoring setup per distinct exposure cluster.
        """
        best_setups: dict[tuple[str, str, str, str], SwingSetup] = {}
        for s in setups:
            key = (s.underlying, s.direction, s.expiry_date, getattr(s, "horizon", "POSITIONAL"))
            if key not in best_setups or s.score.total > best_setups[key].score.total:
                best_setups[key] = s
        return list(best_setups.values())

    async def run_scan(
        self,
        portfolio_equity: float = 1_000_000.0,
        force_refresh: bool = False,
        limit_symbols: Optional[list[str]] = None,
        horizon: str = "ALL",
    ) -> dict[str, Any]:
        """
        Executes complete options swing scanning pipeline across index underlyings.
        """
        async with self._scan_lock:
            start_time = time.time()
            logger.info("swing_options_scan_started")

            # 1. Load persisted state
            state = load_swing_state()
            open_positions: list[SwingPosition] = state.get("open_positions", [])
            closed_positions: list[SwingPosition] = state.get("closed_positions", [])

            # 2. Fetch NIFTY Benchmark candles & evaluate regime
            nifty_candles = await self.fetch_symbol_daily_candles("NIFTY", force_refresh=force_refresh)
            regime = market_regime_classifier.evaluate_benchmark(nifty_candles)

            # 3. Determine target index universe
            target_universe = get_swing_universe()
            if limit_symbols:
                target_syms_set = {s.strip().upper() for s in limit_symbols}
                target_universe = [u for u in target_universe if u.symbol.upper() in target_syms_set]

            # 4. Fetch candles for all universe underlyings
            index_candles_map: dict[str, list[dict[str, Any]]] = {}
            for item in target_universe:
                candles = await self.fetch_symbol_daily_candles(item.symbol, force_refresh=force_refresh)
                if candles:
                    index_candles_map[item.symbol] = candles
                await asyncio.sleep(0.005)

            # 5. Asset relative strength
            nifty_20d_ret = 0.0
            if len(nifty_candles) >= 20:
                c_now = float(nifty_candles[-1]["close"])
                c_20 = float(nifty_candles[-20]["close"])
                nifty_20d_ret = ((c_now - c_20) / c_20) * 100.0 if c_20 > 0 else 0.0
            sectors_map = compute_sector_strengths(index_candles_map, nifty_return_20d=nifty_20d_ret)

            # 6. Evaluate Strategies across Index Options Chains
            discovered_setups: list[SwingSetup] = []
            portfolio_risk_manager.total_equity = portfolio_equity

            for item in target_universe:
                candles = index_candles_map.get(item.symbol)
                if not candles or len(candles) < 25:
                    continue

                try:
                    features = extract_swing_features(candles)
                except Exception:
                    continue

                # Fetch live options chain matrix
                chain = None
                try:
                    chain = await self._options_service.get_option_chain_matrix(item.symbol)
                    chain_dq = validate_option_chain_quality(chain)
                    if chain_dq.severity == "BLOCK":
                        logger.warning("chain_quality_blocked", underlying=item.symbol, reasons=chain_dq.reasons)
                        chain = None
                except Exception as e:
                    logger.debug("options_chain_fetch_failed", underlying=item.symbol, error=str(e)[:150])

                current_iv = (chain.analytics.atm_iv if (chain and chain.analytics and chain.analytics.atm_iv) else 0.16)
                spot_price = chain.spot_price if (chain and chain.spot_price > 0) else features.close

                # Enrich regime with IV if NIFTY
                if item.symbol == "NIFTY":
                    regime = market_regime_classifier.enrich_regime_with_iv(regime, current_iv)

                # A. Positional Daily Strategies Pass
                if horizon.upper() in ("ALL", "POSITIONAL"):
                    for strat in self._positional_strategies:
                        try:
                            setup = strat.evaluate(
                                underlying=item.symbol,
                                features=features,
                                candles=candles,
                                regime=regime,
                                portfolio_equity=portfolio_equity,
                                spot_price=spot_price,
                                options_chain=chain,
                                current_iv=current_iv,
                                iv_percentile=regime.iv_percentile,
                            )
                        except Exception as e:
                            logger.debug("strategy_evaluation_failed", strategy=strat.strategy_id, error=str(e)[:150])
                            setup = None

                        if setup is not None:
                            is_allowed, reason = portfolio_risk_manager.validate_candidate(setup, open_positions)
                            if not is_allowed:
                                setup.signal_state = "BLOCKED"
                                setup.trade_validity.portfolio_valid = False
                                setup.trade_validity.overall_valid = False
                                setup.risk_reasons.append(reason)

                            discovered_setups.append(setup)

                # B. Intraday Same-Day Strategies Pass (15M bars)
                if horizon.upper() in ("ALL", "INTRADAY"):
                    intraday_candles = await self.fetch_symbol_intraday_candles(item.symbol, timeframe="15m", force_refresh=force_refresh)
                    if intraday_candles and len(intraday_candles) >= 5:
                        try:
                            intra_features = extract_intraday_swing_features(intraday_candles)
                            for strat in self._intraday_strategies:
                                try:
                                    setup = strat.evaluate(
                                        underlying=item.symbol,
                                        features=intra_features,
                                        candles=intraday_candles,
                                        regime=regime,
                                        portfolio_equity=portfolio_equity,
                                        spot_price=spot_price,
                                        options_chain=chain,
                                        current_iv=current_iv,
                                        iv_percentile=regime.iv_percentile,
                                    )
                                except Exception as e:
                                    logger.debug("intraday_strategy_evaluation_failed", strategy=strat.strategy_id, error=str(e)[:150])
                                    setup = None

                                if setup is not None:
                                    is_allowed, reason = portfolio_risk_manager.validate_candidate(setup, open_positions)
                                    if not is_allowed:
                                        setup.signal_state = "BLOCKED"
                                        setup.trade_validity.portfolio_valid = False
                                        setup.trade_validity.overall_valid = False
                                        setup.risk_reasons.append(reason)

                                    discovered_setups.append(setup)
                        except Exception as e:
                            logger.debug("intraday_features_failed", symbol=item.symbol, error=str(e)[:150])

            # 7. Deduplicate Correlated Setups & Sort by Score
            discovered_setups = self._deduplicate_setups(discovered_setups)
            discovered_setups.sort(key=lambda s: s.score.total, reverse=True)

            # 8. Update Active Open Positions (Dual-Layer Stop Monitoring)
            updated_open: list[SwingPosition] = []
            for pos in open_positions:
                # Refresh spot price
                und_candles = index_candles_map.get(pos.underlying)
                curr_spot = float(und_candles[-1]["close"]) if und_candles else pos.current_spot

                # Try to get updated premium from live chain or estimate via Delta
                curr_premium = pos.current_premium
                try:
                    chain_pos = await self._options_service.get_option_chain_matrix(pos.underlying, pos.expiry_date)
                    if chain_pos and chain_pos.strikes:
                        for row in chain_pos.strikes:
                            if abs(row.strike - pos.strike) < 1e-4:
                                side = row.call if pos.option_type == "CE" else row.put
                                if side and side.ltp > 0:
                                    curr_premium = side.ltp
                                break
                except Exception:
                    pass

                upd = update_position(
                    position=pos,
                    current_premium=curr_premium,
                    current_spot=curr_spot,
                    current_greeks=pos.greeks_at_entry,
                    current_iv=pos.iv_at_entry,
                    dte_remaining=pos.dte_remaining,
                )

                if upd.status == "CLOSED":
                    closed_positions.append(upd)
                else:
                    updated_open.append(upd)

            # 9. Compute Portfolio Health & Greeks Exposure
            port_state = portfolio_risk_manager.compute_portfolio_state(updated_open)

            # 10. Persist State atomically
            save_swing_state(
                setups=discovered_setups,
                open_positions=updated_open,
                closed_positions=closed_positions,
                regime=regime,
            )
            if self._disk_cache:
                save_candles_cache(self._disk_cache)

            duration = round(time.time() - start_time, 2)
            result = {
                "scan_timestamp_utc": int(time.time() * 1000),
                "duration_seconds": duration,
                "underlyings_scanned": len(index_candles_map),
                "regime": regime.model_dump(mode="json"),
                "sectors": [s.model_dump(mode="json") for s in sectors_map.values()],
                "setups": [s.model_dump(mode="json") for s in discovered_setups],
                "open_positions": [p.model_dump(mode="json") for p in updated_open],
                "closed_positions_count": len(closed_positions),
                "portfolio_risk": port_state.model_dump(mode="json"),
            }
            self._last_scan_result = result
            logger.info(
                "swing_options_scan_completed",
                duration_s=duration,
                setups_found=len(discovered_setups),
                open_positions=len(updated_open),
            )
            return result

    def get_last_result(self) -> dict[str, Any]:
        """Returns the cached result of the last scan."""
        if not self._last_scan_result:
            state = load_swing_state()
            port = portfolio_risk_manager.compute_portfolio_state(state.get("open_positions", []))
            return {
                "scan_timestamp_utc": int(time.time() * 1000),
                "duration_seconds": 0.0,
                "underlyings_scanned": 0,
                "regime": state.get("regime").model_dump(mode="json") if state.get("regime") else None,
                "sectors": [],
                "setups": [s.model_dump(mode="json") for s in state.get("setups", [])],
                "open_positions": [p.model_dump(mode="json") for p in state.get("open_positions", [])],
                "closed_positions_count": len(state.get("closed_positions", [])),
                "portfolio_risk": port.model_dump(mode="json"),
            }
        return self._last_scan_result


swing_scanner = SwingScanner()


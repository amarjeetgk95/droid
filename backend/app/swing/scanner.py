"""
Swing Scanner Engine (v5.0 §23).
Dual-mode scanner:
  1. EOD Scan: Evaluates finalized daily bars across Top 50 stocks + NIFTY.
  2. Intraday Monitor: Checks trigger activations and trailing stops on open positions.
Includes intelligent candle caching to prevent rate-limit throttling (§Nuance 1).
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
    SectorClassification,
    PortfolioRiskState,
)
from app.swing.universe import (
    SWING_EQUITY_UNIVERSE,
    BENCHMARKS,
    get_swing_universe,
)
from app.swing.data_quality import validate_and_clean_daily_candles
from app.swing.technical import extract_swing_features
from app.swing.regime import market_regime_classifier
from app.swing.sector import compute_sector_strengths
from app.swing.strategies.vcp_breakout import VCPBreakoutStrategy
from app.swing.strategies.trend_pullback import TrendPullbackStrategy
from app.swing.strategies.stage2_breakout import Stage2BreakoutStrategy
from app.swing.portfolio_risk import portfolio_risk_manager
from app.swing.lifecycle import update_position_on_candle
from app.swing.persistence import save_swing_state, load_swing_state, save_candles_cache, load_candles_cache

logger = structlog.get_logger()


class SwingScanner:
    def __init__(self, candle_cache_ttl_s: float = 3600.0):
        self.candle_cache_ttl_s = candle_cache_ttl_s
        self._candle_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._disk_cache: dict[str, list[dict[str, Any]]] = load_candles_cache()
        for sym, c_list in self._disk_cache.items():
            if c_list:
                self._candle_cache[sym] = (time.time(), c_list)

        self._strategies = [
            VCPBreakoutStrategy(),
            TrendPullbackStrategy(),
            Stage2BreakoutStrategy(),
        ]
        self._last_scan_result: dict[str, Any] = {}
        self._scan_lock = asyncio.Lock()

    def _get_provider_symbol(self, symbol: str) -> str:
        s = symbol.strip().upper()
        if s in ("NIFTY", "NIFTY 50", "NIFTY50"):
            return "NIFTY 50"
        if s in ("BANKNIFTY", "BANK NIFTY"):
            return "BANKNIFTY"
        if s in ("FINNIFTY", "FIN NIFTY"):
            return "FINNIFTY"
        if s in ("SENSEX",):
            return "SENSEX"
        return f"NSE:{s}-EQ"

    async def fetch_symbol_daily_candles(
        self,
        symbol: str,
        lookback_days: int = 260,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Fetches daily candles with in-memory caching to protect API limits."""
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
            # Clean and validate through Data Quality Firewall
            dq = validate_and_clean_daily_candles(raw_candles, min_required_bars=25)
            if dq.is_valid:
                self._candle_cache[symbol] = (now, dq.cleaned_candles)
                self._disk_cache[symbol] = dq.cleaned_candles
                return dq.cleaned_candles
        except Exception as e:
            logger.debug("swing_fetch_candles_failed", symbol=symbol, error=str(e)[:150])

        # Robustness fallback: If live broker fetch fails (after-hours/session expiry), return disk-cached daily bars
        if symbol in self._disk_cache and len(self._disk_cache[symbol]) >= 25:
            return self._disk_cache[symbol]

        return []

    async def run_scan(
        self,
        portfolio_equity: float = 1_000_000.0,
        force_refresh: bool = False,
        limit_symbols: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Executes complete EOD swing scanning pipeline across the universe.
        """
        async with self._scan_lock:
            start_time = time.time()
            logger.info("swing_scan_started")

            # 1. Load persisted state
            state = load_swing_state()
            open_positions: list[SwingPosition] = state.get("open_positions", [])
            closed_positions: list[SwingPosition] = state.get("closed_positions", [])

            # 2. Fetch NIFTY Benchmark candles
            nifty_candles = await self.fetch_symbol_daily_candles("NIFTY", force_refresh=force_refresh)
            regime = market_regime_classifier.evaluate_benchmark(nifty_candles)

            nifty_20d_ret = 0.0
            if len(nifty_candles) >= 20:
                c_now = float(nifty_candles[-1]["close"])
                c_20 = float(nifty_candles[-20]["close"])
                nifty_20d_ret = ((c_now - c_20) / c_20) * 100.0 if c_20 > 0 else 0.0

            # 3. Determine target universe
            target_universe = get_swing_universe()
            if limit_symbols:
                target_syms_set = {s.strip().upper() for s in limit_symbols}
                target_universe = [u for u in target_universe if u.symbol.upper() in target_syms_set]

            # 4. Fetch candles for all universe stocks (batched concurrency)
            stock_candles_map: dict[str, list[dict[str, Any]]] = {}
            for item in target_universe:
                candles = await self.fetch_symbol_daily_candles(item.symbol, force_refresh=force_refresh)
                if candles:
                    stock_candles_map[item.symbol] = candles
                # Small yield to not freeze event loop
                await asyncio.sleep(0.005)

            # 5. Compute Sector relative strengths
            sectors_map = compute_sector_strengths(stock_candles_map, nifty_return_20d=nifty_20d_ret)

            # 6. Evaluate Strategies & Generate Setups
            discovered_setups: list[SwingSetup] = []
            portfolio_risk_manager.total_equity = portfolio_equity

            for item in target_universe:
                candles = stock_candles_map.get(item.symbol)
                if not candles or len(candles) < 25:
                    continue

                try:
                    features = extract_swing_features(candles)
                except Exception:
                    continue

                sec_status = sectors_map.get(
                    item.sector,
                    SectorClassification(sector=item.sector, trend="NEUTRAL", relative_strength=50.0),
                )

                for strat in self._strategies:
                    setup = strat.evaluate(
                        symbol=item.symbol,
                        sector=item.sector,
                        features=features,
                        candles=candles,
                        regime=regime,
                        sector_status=sec_status,
                        portfolio_equity=portfolio_equity,
                    )
                    if setup is not None:
                        # Pre-Trade Portfolio Risk & Concentration Gate (§15, §16)
                        is_allowed, reason = portfolio_risk_manager.validate_candidate(setup, open_positions)
                        if not is_allowed:
                            setup.signal_state = "BLOCKED"
                            setup.risk_reasons.append(reason)

                        discovered_setups.append(setup)

            # 7. Sort setups by total score descending
            discovered_setups.sort(key=lambda s: s.score.total, reverse=True)

            # 8. Update active open positions against latest candles
            updated_open: list[SwingPosition] = []
            for pos in open_positions:
                p_candles = stock_candles_map.get(pos.symbol)
                if p_candles:
                    latest = p_candles[-1]
                    try:
                        f_pos = extract_swing_features(p_candles)
                        upd = update_position_on_candle(
                            position=pos,
                            candle_close=float(latest["close"]),
                            candle_low=float(latest["low"]),
                            candle_high=float(latest["high"]),
                            current_ema20=f_pos.ema_20,
                            recent_3d_low=min(c["low"] for c in p_candles[-3:]),
                        )
                    except Exception:
                        upd = pos

                    if upd.status == "CLOSED":
                        closed_positions.append(upd)
                    else:
                        updated_open.append(upd)
                else:
                    updated_open.append(pos)

            # 9. Compute Portfolio Health
            port_state = portfolio_risk_manager.compute_portfolio_state(updated_open)

            # 10. Persist State
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
                "stocks_scanned": len(stock_candles_map),
                "regime": regime.model_dump(mode="json"),
                "sectors": [s.model_dump(mode="json") for s in sectors_map.values()],
                "setups": [s.model_dump(mode="json") for s in discovered_setups],
                "open_positions": [p.model_dump(mode="json") for p in updated_open],
                "closed_positions_count": len(closed_positions),
                "portfolio_risk": port_state.model_dump(mode="json"),
            }
            self._last_scan_result = result
            logger.info(
                "swing_scan_completed",
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
                "stocks_scanned": 0,
                "regime": state.get("regime").model_dump(mode="json") if state.get("regime") else None,
                "sectors": [],
                "setups": [s.model_dump(mode="json") for s in state.get("setups", [])],
                "open_positions": [p.model_dump(mode="json") for p in state.get("open_positions", [])],
                "closed_positions_count": len(state.get("closed_positions", [])),
                "portfolio_risk": port.model_dump(mode="json"),
            }
        return self._last_scan_result


swing_scanner = SwingScanner()

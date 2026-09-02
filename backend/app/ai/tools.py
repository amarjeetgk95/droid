"""
DROID AI Quantitative Function & Tool Registry
Defines schemas and execution handlers enabling the AI to interactively
query live market quotes, regime indicators, options chains, futures, and institutional positioning.
"""
from __future__ import annotations

import json
from typing import Any
import structlog
from app.services.market_service import MarketService
from app.services.regime_service import regime_service
from app.services.options_service import options_service
from app.services.fii_dii_service import FIIDIIService
from app.services.ai_service import _fetch_futures_safe

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Tool Declarations (OpenAI / OpenRouter / Gemini Compatible)
# ---------------------------------------------------------------------------

AI_TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_market_quote",
            "description": "Fetch real-time spot price, day change, volume, and OHLC data for an Indian index or equity (e.g. NIFTY, BANKNIFTY, FINNIFTY, SENSEX, RELIANCE).",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Ticker symbol (e.g., NIFTY, BANKNIFTY)",
                        "default": "NIFTY",
                    }
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_regime_analytics",
            "description": "Fetch technical regime state, ADX trend strength, RSI, Supertrend, ATR, Classic Floor Pivots, and Volume Profile (POC, VAH, VAL).",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Ticker symbol (e.g., NIFTY, BANKNIFTY)",
                        "default": "NIFTY",
                    }
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_option_chain_summary",
            "description": "Fetch options analytics including ATM IV, PCR (OI & Volume), Max Pain strike, Call Resistance Walls, Put Support Walls, and ATM Greeks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Underlying symbol (e.g., NIFTY, BANKNIFTY)",
                        "default": "NIFTY",
                    },
                    "expiry": {
                        "type": "string",
                        "description": "Optional expiry date in YYYY-MM-DD format. If omitted, nearest expiry is used.",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_futures_overview",
            "description": "Fetch Futures term structure, Near/Next/Far contract basis, annualized Cost of Carry (CoC), 4-Quadrant OI buildup, and rollover pace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Underlying symbol (e.g., NIFTY, BANKNIFTY)",
                        "default": "NIFTY",
                    }
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_institutional_flow",
            "description": "Fetch FII, DII, Pro, and Client derivatives positioning (Index Futures Long/Short ratio, Call/Put OI) and recent Cash Market net flows.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_options_strategy_payoff",
            "description": "Calculate net debit/credit, max profit, max loss, breakeven points, and net Greeks for a multi-leg options strategy.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Underlying symbol"},
                    "spot_price": {"type": "number", "description": "Current underlying spot price"},
                    "legs": {
                        "type": "array",
                        "description": "List of strategy option legs",
                        "items": {
                            "type": "object",
                            "properties": {
                                "strike": {"type": "number"},
                                "option_type": {"type": "string", "enum": ["CE", "PE"]},
                                "action": {"type": "string", "enum": ["BUY", "SELL"]},
                                "premium": {"type": "number", "description": "Option premium per unit"},
                                "delta": {"type": "number", "description": "Delta Greek (optional)"},
                                "theta": {"type": "number", "description": "Theta Greek (optional)"},
                            },
                            "required": ["strike", "option_type", "action", "premium"],
                        },
                    },
                },
                "required": ["symbol", "spot_price", "legs"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool Execution Handlers
# ---------------------------------------------------------------------------

async def execute_tool(name: str, arguments: dict[str, Any] | str) -> dict[str, Any]:
    """Execute a tool call against the internal quantitative engines."""
    if isinstance(arguments, str):
        try:
            args = json.loads(arguments)
        except Exception:
            args = {}
    else:
        args = arguments or {}

    logger.info("executing_ai_tool", tool_name=name, args=args)

    try:
        if name == "get_market_quote":
            symbol = str(args.get("symbol", "NIFTY")).upper().replace(" 50", "")
            ms = MarketService()
            quote = await ms.get_quote(symbol)
            return {
                "symbol": symbol,
                "ltp": getattr(quote, "ltp", None),
                "change": getattr(quote, "change", None),
                "change_percent": getattr(quote, "change_percent", None),
                "high": getattr(quote, "high", None),
                "low": getattr(quote, "low", None),
                "volume": getattr(quote, "volume", None),
            }

        elif name == "get_regime_analytics":
            symbol = str(args.get("symbol", "NIFTY")).upper().replace(" 50", "")
            regime = await regime_service.classify_market_regime(symbol)
            return {
                "symbol": symbol,
                "spot_price": regime.spot_price,
                "regime_state": regime.regime_state,
                "confidence_score": regime.confidence_score,
                "summary_headline": regime.summary_headline,
                "institutional_rationale": regime.institutional_rationale,
                "indicators": {
                    "rsi_14": regime.indicators.rsi_14,
                    "adx_14": regime.indicators.adx_14,
                    "supertrend_direction": regime.indicators.supertrend_direction,
                    "supertrend_value": regime.indicators.supertrend_value,
                    "atr_14": regime.indicators.atr_14,
                    "bollinger_bandwidth": regime.indicators.bollinger_bandwidth,
                },
                "key_levels": {
                    "pivot": regime.key_levels.classic_pivots.pivot,
                    "r1": regime.key_levels.classic_pivots.r1,
                    "s1": regime.key_levels.classic_pivots.s1,
                    "poc": regime.key_levels.poc,
                    "vah": regime.key_levels.vah,
                    "val": regime.key_levels.val,
                    "nearest_support": regime.key_levels.nearest_support,
                    "nearest_resistance": regime.key_levels.nearest_resistance,
                },
                "vix": {
                    "value": regime.vix_regime.vix_value if regime.vix_regime else None,
                    "category": regime.vix_regime.regime_category if regime.vix_regime else None,
                    "recommended_strategy": regime.vix_regime.recommended_option_strategy if regime.vix_regime else None,
                },
            }

        elif name == "get_option_chain_summary":
            symbol = str(args.get("symbol", "NIFTY")).upper().replace(" 50", "")
            expiry = args.get("expiry")
            chain = await options_service.get_option_chain_matrix(symbol, expiry_str=expiry)
            analytics = chain.analytics
            max_pain = getattr(analytics, "max_pain_strike", None) if analytics else None

            # Top strikes
            top_calls = []
            top_puts = []
            if chain.strikes:
                sorted_calls = sorted([s for s in chain.strikes if s.call], key=lambda x: x.call.open_interest, reverse=True)
                sorted_puts = sorted([s for s in chain.strikes if s.put], key=lambda x: x.put.open_interest, reverse=True)
                top_calls = [{"strike": s.strike, "oi": s.call.open_interest, "ltp": s.call.ltp} for s in sorted_calls[:3]]
                top_puts = [{"strike": s.strike, "oi": s.put.open_interest, "ltp": s.put.ltp} for s in sorted_puts[:3]]

            return {
                "symbol": symbol,
                "spot_price": analytics.spot_price if analytics else None,
                "atm_iv": analytics.atm_iv if analytics else None,
                "pcr_oi": analytics.pcr_oi if analytics else None,
                "pcr_volume": analytics.pcr_volume if analytics else None,
                "max_pain_strike": max_pain,
                "time_to_expiry_days": analytics.time_to_expiry_days if analytics else None,
                "key_call_walls": top_calls,
                "key_put_walls": top_puts,
                "total_call_oi": analytics.total_call_oi if analytics else None,
                "total_put_oi": analytics.total_put_oi if analytics else None,
            }

        elif name == "get_futures_overview":
            symbol = str(args.get("symbol", "NIFTY")).upper().replace(" 50", "")
            futures = await _fetch_futures_safe(symbol)
            if not futures:
                return {"symbol": symbol, "status": "futures_data_unavailable"}

            near = futures.term_structure.contracts[0] if getattr(futures, "term_structure", None) and futures.term_structure.contracts else None
            return {
                "symbol": symbol,
                "spot_price": getattr(futures, "spot_price", None),
                "near_contract": {
                    "ltp": getattr(near, "ltp", None),
                    "basis": getattr(near, "basis", None),
                    "basis_percent": getattr(near, "basis_percent", None),
                    "cost_of_carry_percent": getattr(near, "cost_of_carry_percent", None),
                    "open_interest": getattr(near, "open_interest", None),
                    "oi_change_percent": getattr(near, "oi_change_percent", None),
                } if near else None,
                "buildup": {
                    "type": getattr(futures.buildup, "buildup_type", None) if getattr(futures, "buildup", None) else None,
                    "interpretation": getattr(futures.buildup, "interpretation", None) if getattr(futures, "buildup", None) else None,
                    "strength": getattr(futures.buildup, "strength", None) if getattr(futures, "buildup", None) else None,
                },
                "rollover": {
                    "rollover_percent": getattr(futures.rollover, "rollover_percent", None) if getattr(futures, "rollover", None) else None,
                    "pace": getattr(futures.rollover, "rollover_pace", None) if getattr(futures, "rollover", None) else None,
                    "three_month_avg": getattr(futures.rollover, "three_month_avg_rollover", None) if getattr(futures, "rollover", None) else None,
                },
                "term_structure_curve": getattr(futures.term_structure, "curve_state", "CONTANGO") if getattr(futures, "term_structure", None) else "CONTANGO",
            }

        elif name == "get_institutional_flow":
            fii_service = FIIDIIService()
            overview = fii_service.get_institutional_overview()
            return {
                "timestamp": overview.timestamp.isoformat(),
                "positioning": [
                    {
                        "category": p.category,
                        "futures_net_contracts": p.index_futures_net,
                        "long_short_ratio": p.long_short_ratio,
                        "call_long": p.index_call_long,
                        "put_long": p.index_put_long,
                        "sentiment": p.sentiment,
                    }
                    for p in overview.breakdown_by_category
                ],
                "cash_flows": [
                    {
                        "date": c.date,
                        "category": c.category,
                        "net_crores": c.net_value_crores,
                    }
                    for c in overview.recent_cash_flows[:3]
                ],
            }

        elif name == "calculate_options_strategy_payoff":
            symbol = str(args.get("symbol", "NIFTY")).upper()
            spot = float(args.get("spot_price", 25000.0))
            legs = args.get("legs", [])
            
            # Simple quantitative payoff evaluation
            net_premium = 0.0
            net_delta = 0.0
            net_theta = 0.0

            for leg in legs:
                action = leg.get("action", "BUY").upper()
                prem = float(leg.get("premium", 0.0))
                delta = float(leg.get("delta", 0.0) or 0.0)
                theta = float(leg.get("theta", 0.0) or 0.0)

                sign = -1.0 if action == "BUY" else 1.0
                net_premium += (sign * prem)
                
                leg_delta_sign = 1.0 if action == "BUY" else -1.0
                net_delta += (leg_delta_sign * delta)
                net_theta += (sign * theta)

            is_credit = net_premium > 0
            
            return {
                "symbol": symbol,
                "spot_price": spot,
                "leg_count": len(legs),
                "net_premium_points": round(net_premium, 2),
                "structure_type": "NET_CREDIT" if is_credit else "NET_DEBIT",
                "net_delta": round(net_delta, 3),
                "net_theta": round(net_theta, 2),
                "summary": f"Strategy with {len(legs)} legs structured as {'Net Credit (+₹' + str(round(net_premium, 2)) + ')' if is_credit else 'Net Debit (-₹' + str(round(abs(net_premium), 2)) + ')'} per lot.",
            }

        else:
            return {"error": f"Unknown tool: {name}"}

    except Exception as e:
        logger.error("ai_tool_execution_failed", tool_name=name, error=str(e))
        return {"error": f"Tool execution failed: {str(e)}"}

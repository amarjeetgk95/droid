"""Intent Router (spec §3).

Deterministic keyword/regex rules run first and are authoritative for every
vocabulary DROID already knows. An LLM classifier is only ever consulted when
no rule matches — it can never override a deterministic match, and it can never
widen the instrument list.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.copilot.enums import DEFAULT_SYMBOL, SUPPORTED_SYMBOLS
from app.copilot.models import IntentDecision

# --------------------------------------------------------------------------- #
# Tool plans by intent (spec §22) — an intent never calls every tool.
# --------------------------------------------------------------------------- #
INTENT_TOOL_PLAN: dict[str, list[str]] = {
    "NEXT_SESSION_OUTLOOK": [
        "quote", "regime", "technicals", "options", "futures", "flow", "historical",
    ],
    "INTRADAY_OUTLOOK": ["quote", "regime", "technicals", "options", "futures", "flow"],
    "MARKET_STATUS": ["quote", "regime", "technicals", "options"],
    "BREAKOUT_ANALYSIS": [
        "quote", "technicals", "volume", "market_structure", "options", "futures",
        "regime", "historical",
    ],
    "OPTIONS_ANALYSIS": ["quote", "options", "oi", "iv", "pcr", "max_pain", "walls"],
    "SUPPORT_RESISTANCE": [
        "quote", "market_structure", "volume_profile", "technical_levels", "options_levels",
    ],
    "SIGNAL_VALIDATION": [
        "quote", "strategy_signal", "regime", "technicals", "options", "futures", "risk_engine",
    ],
    "TRADE_SETUP_ANALYSIS": [
        "quote", "technicals", "options", "futures", "regime", "risk_engine",
    ],
    "REGIME_ANALYSIS": ["quote", "regime", "technicals", "vix"],
    "WHY_MOVE": ["quote", "regime", "technicals", "futures", "flow", "options"],
    "HISTORICAL_ANALOG": ["quote", "technicals", "historical_analogs"],
    "GENERAL_MARKET_QUESTION": ["quote", "regime", "technicals"],
}

#: Which gatherers (real parallel network calls) each tool id needs.
TOOL_GATHERERS: dict[str, tuple[str, ...]] = {
    "quote": ("quote",),
    "regime": ("regime",),
    "technicals": ("regime",),
    "vix": ("regime",),
    "market_structure": ("regime", "quote"),
    "volume_profile": ("regime",),
    "technical_levels": ("regime",),
    "volume": ("regime",),
    "options": ("options",),
    "oi": ("options",),
    "iv": ("options",),
    "pcr": ("options",),
    "max_pain": ("options",),
    "walls": ("options",),
    "options_levels": ("options",),
    "futures": ("futures",),
    "flow": ("flow",),
    "historical": ("historical",),
    "historical_analogs": ("historical",),
    "strategy_signal": (),
    "risk_engine": (),
}

# --------------------------------------------------------------------------- #
# Rule tables
# --------------------------------------------------------------------------- #
_INTENT_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "SIGNAL_VALIDATION",
        "signal_validation",
        re.compile(
            r"\b(validate|validation|valid(?:ate)?\s+(?:this|the)\s+signal|is\s+this\s+signal"
            r"|signal\s+(?:still\s+)?valid|approve|should\s+i\s+(?:take|enter)|"
            r"long\s+signal|short\s+signal|check\s+the\s+gates?)\b",
            re.I,
        ),
    ),
    (
        "BREAKOUT_ANALYSIS",
        "breakout",
        re.compile(
            r"\b(break(?:out|down|s)?|sustain(?:ed)?\s+above|"
            r"cross(?:es|ing)?\s+above|take\s+out|clear\s+the\s+level|retest)\b",
            re.I,
        ),
    ),
    (
        "HISTORICAL_ANALOG",
        "historical_analog",
        re.compile(
            r"\b(historical|analog(?:ue)?s?|similar\s+(?:sessions?|days?|setups?)|"
            r"in\s+the\s+past|precedent|history\s+of)\b",
            re.I,
        ),
    ),
    (
        "WHY_MOVE",
        "why_move",
        re.compile(
            r"\b(why\s+(?:did|is|has|are|was)|what\s+caused|reason\s+(?:for|behind)|"
            r"explain\s+(?:the|this)\s+(?:move|fall|drop|rally|spike))\b",
            re.I,
        ),
    ),
    (
        "OPTIONS_ANALYSIS",
        "options",
        re.compile(
            r"\b(option(?:s)?|option\s+chain|pcr|put[- ]call|max\s*pain|call\s+wall|"
            r"put\s+wall|call\s+writing|put\s+writing|open\s+interest|\boi\b|implied\s+vol|"
            r"\biv\b|expiry|expiries|straddle|strangle|premium|greeks)\b",
            re.I,
        ),
    ),
    (
        "SUPPORT_RESISTANCE",
        "support_resistance",
        re.compile(
            r"\b(support|resistance|s\s*/\s*r|levels?|key\s+levels?|pivot(?:s)?|"
            r"value\s+area|poc|vah|val|where\s+(?:is|are)\s+the)\b",
            re.I,
        ),
    ),
    (
        "TRADE_SETUP_ANALYSIS",
        "trade_setup",
        re.compile(
            r"\b(trade\s+setup|setup|entry\s+and\s+exit|entry|stop\s*loss|\bsl\b|"
            r"target|risk[- ]reward|position\s+siz)\b",
            re.I,
        ),
    ),
    (
        "REGIME_ANALYSIS",
        "regime",
        re.compile(
            r"\b(regime|trend(?:ing)?|range[- ]?bound|rangebound|chop(?:py)?|adx|"
            r"trend\s+strength|volatility\s+(?:state|regime))\b",
            re.I,
        ),
    ),
    (
        "NEXT_SESSION_OUTLOOK",
        "outlook_next_session",
        re.compile(
            r"\b(predict(?:ion)?|forecast|outlook|next\s+day|next\s+session|"
            r"tomorrow|bias\s+for\s+(?:tomorrow|the\s+next)|view\s+for\s+tomorrow)\b",
            re.I,
        ),
    ),
    (
        "INTRADAY_OUTLOOK",
        "outlook_intraday",
        re.compile(
            r"\b(intraday|rest\s+of\s+the\s+day|next\s+(?:15|30|60)\s*min(?:ute)?s?|"
            r"next\s+(?:hour|1\s*hour)|today'?s?\s+(?:move|outlook|bias)|"
            r"what\s+is\s+happening)\b",
            re.I,
        ),
    ),
    (
        "MARKET_STATUS",
        "market_status",
        re.compile(
            r"\b(market\s+status|status\s+of\s+the\s+market|market\s+open|is\s+the\s+market|"
            r"right\s+now|currently|current\s+(?:price|level)|live\s+price|quote|"
            r"how\s+much\s+is|bullish\s+now|bearish\s+now|where\s+is\s+\w+\s+trading)\b",
            re.I,
        ),
    ),
)

_HORIZON_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "SWING_3_5_DAYS",
        "swing",
        re.compile(r"\b(swing|3\s*(?:-|to)\s*5\s*days?|this\s+week|next\s+week|few\s+days|weekly)\b", re.I),
    ),
    (
        "NEXT_SESSION",
        "next_session",
        re.compile(
            r"\b(next\s+day|next\s+session|tomorrow|overnight|next\s+trading\s+day|"
            r"closing\s+bell|eod|end\s+of\s+day|positional)\b",
            re.I,
        ),
    ),
    (
        "NEXT_15_MIN",
        "next_15_min",
        re.compile(r"\b(15\s*(?:m|min|mins|minute|minutes)|quarter\s+hour|next\s+15)\b", re.I),
    ),
    (
        "NEXT_60_MIN",
        "next_60_min",
        re.compile(r"\b(60\s*(?:m|min|mins|minute|minutes)|1\s*hour|next\s+hour|hourly)\b", re.I),
    ),
)

_STATUS_WORDS = re.compile(
    r"\b(bullish|bearish|neutral|up|down|rising|falling|strong|weak|momentum|"
    r"sentiment|trending|what'?s\s+happening|market\s+doing)\b",
    re.I,
)

_BREAKOUT_LEVEL_RE = re.compile(r"\b(\d{2,3}(?:,\d{3})+|\d{4,6}(?:\.\d+)?)\b")

_UNSUPPORTED_HINTS = re.compile(
    r"\b(finnifty|midcap|nifty\s*it|bankex|dow|nasdaq|s&p|crude|gold|btc|bitcoin|"
    r"reliance|tcs|hdfc|infy)\b",
    re.I,
)


@dataclass
class IntentContext:
    """Caller-supplied context the router must respect."""

    ui_symbol: str = DEFAULT_SYMBOL
    default_horizon: str | None = None
    has_signal: bool = False


class IntentRouter:
    """Deterministic-first intent/symbol/horizon resolution."""

    def decide(
        self,
        query: str,
        context: IntentContext | None = None,
        symbol: str | None = None,
        requested_horizon: str | None = None,
        requested_intent: str | None = None,
    ) -> IntentDecision:
        ctx = context or IntentContext()
        text = (query or "").strip()
        warnings: list[str] = []

        resolved_symbol, symbol_warning = self.resolve_symbol(text, explicit=symbol, ui_symbol=ctx.ui_symbol)
        if symbol_warning:
            warnings.append(symbol_warning)

        horizon, horizon_rule = self.resolve_horizon(text, ctx)
        if requested_horizon in ("NEXT_15_MIN", "NEXT_60_MIN", "TODAY", "NEXT_SESSION", "SWING_3_5_DAYS"):
            horizon, horizon_rule = requested_horizon, "request_horizon"

        intent, matched_rule = self.resolve_intent(text, horizon, ctx)
        if requested_intent in INTENT_TOOL_PLAN:
            intent, matched_rule = requested_intent, "request_intent"

        tool_plan = list(INTENT_TOOL_PLAN.get(intent, INTENT_TOOL_PLAN["GENERAL_MARKET_QUESTION"]))
        depth = self.resolve_depth(text, requested=None)
        breakout_level = self._extract_level(text) if intent == "BREAKOUT_ANALYSIS" else None

        return IntentDecision(
            intent=intent,
            symbol=resolved_symbol,
            horizon=horizon,
            analysis_depth=depth,
            requires_options=any(
                t in tool_plan for t in ("options", "oi", "iv", "pcr", "max_pain", "walls", "options_levels")
            ),
            requires_futures="futures" in tool_plan,
            requires_flow="flow" in tool_plan,
            requires_historical=any(t in tool_plan for t in ("historical", "historical_analogs")),
            requires_signal_validation=intent == "SIGNAL_VALIDATION",
            requires_breakout=intent == "BREAKOUT_ANALYSIS",
            tool_plan=tool_plan,
            matched_rule=f"{matched_rule}|{horizon_rule}" if horizon_rule else matched_rule,
            classifier="RULES",
            confidence=0.92 if matched_rule != "fallback" else 0.4,
            breakout_level=breakout_level,
            warnings=warnings,
        )



    # ------------------------------------------------------------------ #
    # Symbol
    # ------------------------------------------------------------------ #
    def resolve_symbol(
        self,
        text: str,
        explicit: str | None = None,
        ui_symbol: str = DEFAULT_SYMBOL,
    ) -> tuple[str, str | None]:
        """Resolve the instrument. Never silently substitutes a different one."""
        ui = self._canonical(ui_symbol) or DEFAULT_SYMBOL
        if explicit and str(explicit).strip():
            canon = self._canonical(explicit)
            if canon:
                return canon, None
            return ui, (
                f"'{explicit}' is not a supported DROID instrument (NIFTY, BANKNIFTY, SENSEX). "
                f"Analysis uses the selected instrument {ui}."
            )
        for sym in SUPPORTED_SYMBOLS:
            if re.search(rf"\b{re.escape(sym)}\b", text, re.I):
                return sym, None
        if re.search(r"\bbank\s*nifty\b", text, re.I):
            return "BANKNIFTY", None
        if re.search(r"\bsensex\b", text, re.I):
            return "SENSEX", None
        if re.search(r"\bnifty\b", text, re.I):
            return "NIFTY", None
        unsupported = _UNSUPPORTED_HINTS.search(text)
        if unsupported:
            return ui, (
                f"'{unsupported.group(1)}' is outside DROID's supported set (NIFTY, BANKNIFTY, SENSEX). "
                f"Analysis uses the selected instrument {ui}."
            )
        return ui, None

    @staticmethod
    def _canonical(value: str | None) -> str | None:
        if not value:
            return None
        compact = re.sub(r"[^A-Za-z0-9]", "", str(value)).upper()
        for sym in SUPPORTED_SYMBOLS:
            if compact == sym:
                return sym
        return {
            "NIFTY50": "NIFTY",
            "BSESENSEX": "SENSEX",
            "NIFTYBANK": "BANKNIFTY",
            "BANKNIFTYINDEX": "BANKNIFTY",
        }.get(compact)

    # ------------------------------------------------------------------ #
    # Horizon
    # ------------------------------------------------------------------ #
    def resolve_horizon(self, text: str, context: IntentContext) -> tuple[str, str | None]:
        for horizon, rule, pattern in _HORIZON_RULES:
            if pattern.search(text):
                return horizon, rule
        if context.default_horizon:
            return context.default_horizon, "context_default"
        return "TODAY", None

    # ------------------------------------------------------------------ #
    # Intent
    # ------------------------------------------------------------------ #
    def resolve_intent(self, text: str, horizon: str, context: IntentContext) -> tuple[str, str]:
        if text:
            for intent, rule, pattern in _INTENT_RULES:
                if not pattern.search(text):
                    continue
                if intent == "MARKET_STATUS" and not _STATUS_WORDS.search(text):
                    continue
                return intent, rule
        if context.has_signal and re.search(r"\b(this|the)\s+(?:long|short|signal|trade)\b", text, re.I):
            return "SIGNAL_VALIDATION", "signal_context"
        if horizon == "SWING_3_5_DAYS":
            return "NEXT_SESSION_OUTLOOK", "swing_horizon"
        if horizon in ("NEXT_15_MIN", "NEXT_60_MIN"):
            return "INTRADAY_OUTLOOK", "intraday_horizon"
        if not text:
            return "MARKET_STATUS", "empty_query"
        return "GENERAL_MARKET_QUESTION", "fallback"

    # ------------------------------------------------------------------ #
    # Depth / level extraction
    # ------------------------------------------------------------------ #
    def resolve_depth(self, text: str, requested: str | None) -> str:
        if requested in ("BRIEF", "STANDARD", "DEEP"):
            return requested
        if re.search(r"\b(deep|detailed|in\s+depth|full\s+analysis|thorough)\b", text, re.I):
            return "DEEP"
        if re.search(r"\b(brief|quick|short|tldr|one\s+line)\b", text, re.I):
            return "BRIEF"
        return "STANDARD"

    @staticmethod
    def _extract_level(text: str) -> float | None:
        """Pull an explicit breakout level ("will SENSEX break 75,000?")."""
        match = _BREAKOUT_LEVEL_RE.search(text or "")
        if not match:
            return None
        try:
            return float(match.group(1).replace(",", ""))
        except ValueError:
            return None


intent_router = IntentRouter()


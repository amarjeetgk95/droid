"""
Telegram Message Templates — §§14-24, 30, 38
Pure rendering layer. Templates NEVER invent data — every value must come from the
authoritative SignalEvent payload produced by the Signal Engine / Outcome Engine /
Risk Engine / Execution Engine. Missing optional values are simply omitted.

Timeframe rule (§13): the candle timeframe displayed is always the
`candle_timeframe` carried by the authoritative signal event. 1M messages are
visually distinct from 5M messages.
"""
from __future__ import annotations

from typing import Any

from app.institutional.telegram_notifications import SignalEvent

DIRECTION_LONG = {"BULLISH", "LONG", "BUY"}
DIRECTION_SHORT = {"BEARISH", "SHORT", "SELL"}


def _fmt(value: Any) -> str:
    """Format a numeric value with thousands separators when possible."""
    if value is None:
        return ""
    try:
        return f"{float(value):,.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def _direction_word(direction: str) -> str:
    d = (direction or "").upper()
    if d in DIRECTION_LONG:
        return "LONG"
    if d in DIRECTION_SHORT:
        return "SHORT"
    return d or "NEUTRAL"


def _header_emoji(event: SignalEvent) -> str:
    if event.candle_timeframe.upper() == "1M":
        return "⚡"  # 1-minute messages visually distinct (§16)
    return "🟢" if _direction_word(event.direction) == "LONG" else "🔴"


def _label(event: SignalEvent) -> str:
    """e.g. 'NIFTY 5M BREAKOUT' / 'BANKNIFTY 1M BREAKDOWN'."""
    setup = (event.setup_type or "BREAKOUT").upper()
    return f"{event.instrument} {event.candle_timeframe.upper()} {setup}"


def _options_block(event: SignalEvent) -> list[str]:
    lines: list[str] = []
    if event.options_status:
        lines.append(f"Options:\n{event.options_status.upper()}")
    if event.major_call_resistance is not None:
        lines.append(f"Major Call Resistance:\n{_fmt(event.major_call_resistance)}")
    if event.major_put_support is not None:
        lines.append(f"Major Put Support:\n{_fmt(event.major_put_support)}")
    if event.oi_pcr is not None:
        lines.append(f"OI PCR:\n{_fmt(event.oi_pcr)}")
    if event.futures_status:
        lines.append(f"Futures:\n{event.futures_status.upper()}")
    return lines


# ── §14 Developing setup ─────────────────────────────────────────────
def format_possible_setup(event: SignalEvent) -> str:
    lines = [
        f"🟡 {_label(event)} DEVELOPING",
        "",
        f"Direction: {_direction_word(event.direction)}",
    ]
    if event.current_price is not None:
        lines.append(f"\nCurrent Price: {_fmt(event.current_price)}")
    if event.trigger_level is not None:
        lines.append(f"Trigger: {_fmt(event.trigger_level)}")
    if event.breakout_pressure is not None:
        lines.append(f"\nBreakout Pressure: {event.breakout_pressure}/100")
    if event.false_breakout_risk is not None:
        lines.append(f"False Breakout Risk: {_fmt(event.false_breakout_risk)}%")
    lines.append("")
    lines.extend(_options_block(event) or ["Options:\nN/A"])
    lines.append("\nStatus:\nWAITING FOR TRIGGER")
    lines.append(f"\nSignal ID:\n{event.signal_id}")
    return "\n".join(lines)


# ── §15/§16/§17 Triggered / Confirmed (also 1M & breakdown) ─────────
def format_signal_state(event: SignalEvent) -> str:
    """TRIGGERED / CONFIRMED / INVALIDATED / EXPIRED states."""
    emoji = _header_emoji(event)
    status = (event.status or event.event_type.replace("SIGNAL_", "")).upper()
    lines = [f"{emoji} {_label(event)} {status}", "", f"Direction:\n{_direction_word(event.direction)}"]
    if event.status:
        lines.append(f"\nStatus:\n{event.status.upper()}")
    if event.trigger_level is not None:
        lines.append(f"\nTrigger:\n{_fmt(event.trigger_level)}")
    if event.current_price is not None:
        lines.append(f"Current:\n{_fmt(event.current_price)}")
    # Entry/Stop/Target ONLY when present in the authoritative signal (§15)
    if event.entry_low is not None or event.entry_high is not None:
        lo, hi = _fmt(event.entry_low), _fmt(event.entry_high)
        lines.append(f"\nEntry:\n{lo}–{hi}" if hi and hi != lo else f"\nEntry:\n{lo}")
    if event.stop_loss is not None:
        lines.append(f"Stop:\n{_fmt(event.stop_loss)}")
    if event.target_low is not None or event.target_high is not None:
        lo, hi = _fmt(event.target_low), _fmt(event.target_high)
        lines.append(f"Target:\n{lo}–{hi}" if hi and hi != lo else f"Target:\n{lo}")
    if event.confidence is not None:
        lines.append(f"\nConfidence:\n{event.confidence}%")
    opt_lines = _options_block(event)
    if opt_lines:
        lines.append("")
        lines.extend(opt_lines)
    if event.ai_status:
        lines.append(f"\nAI:\n{event.ai_status.upper()}")
    if event.risk_status:
        lines.append(f"Risk:\n{event.risk_status.upper()}")
    if event.breakout_pressure is not None:
        lines.append(f"\nBreakout Pressure:\n{event.breakout_pressure}/100")
    if event.false_breakout_risk is not None:
        lines.append(f"False Breakout Risk:\n{_fmt(event.false_breakout_risk)}%")
    lines.append(f"\nSignal ID:\n{event.signal_id}")
    return "\n".join(lines)


# ── §19 AI confirmation ──────────────────────────────────────────────
def format_ai_confirmation(event: SignalEvent) -> str:
    lines = [
        "🧠 AI CONFIRMATION",
        "",
        _label(event),
        "",
        f"Decision:\n{(event.ai_decision or 'N/A').upper()}",
        f"Direction:\n{_direction_word(event.direction)}",
    ]
    if event.ai_confidence is not None:
        lines.append(f"Confidence:\n{event.ai_confidence}%")
    if event.ai_supporting:
        lines.append("\nSupporting:")
        lines.extend(f"• {s}" for s in event.ai_supporting)
    if event.ai_conflicts:
        lines.append("\nConflicts:")
        lines.extend(f"• {c}" for c in event.ai_conflicts)
    lines.append(f"\nSignal:\n{event.signal_id}")
    return "\n".join(lines)


# ── §20 Risk ─────────────────────────────────────────────────────────
def format_risk(event: SignalEvent) -> str:
    rejected = (event.risk_status or "").upper() == "REJECTED"
    lines = [
        "⛔ RISK REJECTED" if rejected else "🛡 RISK APPROVED",
        "",
        _label(event),
        "",
    ]
    if rejected:
        lines.append("Reason:")
        lines.append(event.risk_reason or "Risk limits exceeded.")
        lines.append("\nNo order submitted.")
    else:
        if event.risk_portfolio:
            lines.append(f"Portfolio Risk:\n{event.risk_portfolio.upper()}")
        if event.risk_exposure:
            lines.append(f"Exposure:\n{event.risk_exposure}")
        if event.risk_margin:
            lines.append(f"Margin:\n{event.risk_margin.upper()}")
        if event.risk_correlation:
            lines.append(f"Correlation Risk:\n{event.risk_correlation.upper()}")
    lines.append(f"\nSignal:\n{event.signal_id}")
    return "\n".join(lines)


# ── §21 Execution ────────────────────────────────────────────────────
def format_execution(event: SignalEvent) -> str:
    lines = [
        "✅ ORDER EXECUTED",
        "",
        _label(event),
        "",
        f"Direction:\n{_direction_word(event.direction)}",
    ]
    if event.requested_qty is not None:
        lines.append(f"\nRequested:\n{_fmt(event.requested_qty)}")
    if event.filled_qty is not None:
        lines.append(f"Filled:\n{_fmt(event.filled_qty)}")
    if event.average_fill_price is not None:
        lines.append(f"Average Fill:\n{_fmt(event.average_fill_price)}")
    if event.broker_order_id:
        lines.append(f"\nBroker Order:\n{event.broker_order_id}")
    lines.append(f"\nSignal:\n{event.signal_id}")
    return "\n".join(lines)


# ── §22 Partial fill ─────────────────────────────────────────────────
def format_partial_fill(event: SignalEvent) -> str:
    lines = [
        "⚠ PARTIAL FILL",
        "",
        _label(event),
        "",
        f"Direction:\n{_direction_word(event.direction)}",
    ]
    if event.requested_qty is not None:
        lines.append(f"\nRequested:\n{_fmt(event.requested_qty)}")
    if event.filled_qty is not None:
        lines.append(f"Filled:\n{_fmt(event.filled_qty)}")
    if event.remaining_qty is not None:
        lines.append(f"Remaining:\n{_fmt(event.remaining_qty)}")
    if event.average_fill_price is not None:
        lines.append(f"\nAverage Fill:\n{_fmt(event.average_fill_price)}")
    lines.append("\nStatus:\nPARTIALLY_FILLED")
    if event.remaining_action:
        lines.append(f"\nRemaining Action:\n{event.remaining_action.upper()}")
    lines.append(f"\nSignal:\n{event.signal_id}")
    return "\n".join(lines)


# ── §23/§24 Signal result — theoretical vs actual kept separate ──────
def format_signal_result(event: SignalEvent) -> str:
    result = (event.result or "UNKNOWN").upper()
    if result in ("AMBIGUOUS", "AMBIGUOUS_OUTCOME"):
        lines = ["⚠ SIGNAL RESULT", "", "Result:\nAMBIGUOUS OUTCOME"]
        if event.result_reason:
            lines.append(f"\nReason:\n{event.result_reason}")
        lines.append("\nNo win/loss classification assigned.")
        lines.append(f"\nSignal:\n{event.signal_id}")
        return "\n".join(lines)
    emoji = "✅" if "TARGET" in result else ("❌" if "STOP" in result else "ℹ️")
    lines = [f"{emoji} SIGNAL RESULT", "", _label(event), "", f"Result:\n{result}"]
    if event.theoretical_entry is not None:
        lines.append(f"\nTheoretical Entry:\n{_fmt(event.theoretical_entry)}")
    if event.exit_price is not None:
        lines.append(f"Exit:\n{_fmt(event.exit_price)}")
    if event.theoretical_pnl_points is not None:
        sign = "+" if float(event.theoretical_pnl_points) >= 0 else ""
        lines.append(f"\nTheoretical P&L:\n{sign}{_fmt(event.theoretical_pnl_points)} points")
    if event.holding_time:
        lines.append(f"\nHolding Time:\n{event.holding_time}")
    # Theoretical vs actual P&L NEVER combined into one number (§24)
    if event.theoretical_pnl_amount is not None:
        sign = "+" if float(event.theoretical_pnl_amount) >= 0 else ""
        lines.append(f"\nSignal P&L:\n{sign}₹{_fmt(abs(float(event.theoretical_pnl_amount)))}")
    if event.actual_pnl_amount is not None:
        sign = "+" if float(event.actual_pnl_amount) >= 0 else ""
        lines.append(f"Actual Trade P&L:\n{sign}₹{_fmt(abs(float(event.actual_pnl_amount)))}")
    if event.result_reason and "TARGET" not in result and "STOP" not in result:
        lines.append(f"\nReason:\n{event.result_reason}")
    lines.append(f"\nSignal:\n{event.signal_id}")
    return "\n".join(lines)


# ── §30 Test message — always labeled as a test (§38) ────────────────
def format_test_message(environment: str) -> str:
    return (
        "✅ Telegram Connected\n\n"
        "Your trading signal notifications are working.\n\n"
        f"Environment:\n{environment.upper()}\n\n"
        "TEST MESSAGE — not a trading signal."
    )


def format_link_success(bot_username: str) -> str:
    return (
        "✅ Telegram Connected\n\n"
        "This chat is now linked to your trading account.\n"
        "You will receive 1M/5M breakout signal notifications here.\n\n"
        f"Bot: @{bot_username}\n\n"
        "Available commands:\n"
        "/status /market /signal /positions /pnl /risk /alerts /settings"
    )


def format_link_failure(reason: str) -> str:
    return (
        "❌ LINKING FAILED\n\n"
        f"Reason: {reason}\n\n"
        "Open the web app → Settings → Telegram → CONNECT TELEGRAM "
        "to generate a fresh link token, then send /start <token> here."
    )


# ── §27 Read-only command replies ────────────────────────────────────
def format_status_reply(linked: bool, bot_username: str, environment: str) -> str:
    return (
        "📊 STATUS\n\n"
        f"Telegram: {'CONNECTED' if linked else 'NOT CONNECTED'}\n"
        f"Bot: @{bot_username}\n"
        f"Environment: {environment.upper()}\n\n"
        "Notifications: 1M/5M breakout signals, AI confirmation, risk, execution, results."
    )


def render_event_message(event: SignalEvent) -> str:
    """Dispatch to the right template for an event type."""
    et = event.event_type
    if et == "POSSIBLE_SETUP":
        return format_possible_setup(event)
    if et == "AI_CONFIRMED":
        return format_ai_confirmation(event)
    if et in ("RISK_APPROVED", "RISK_REJECTED"):
        return format_risk(event)
    if et == "EXECUTED":
        return format_execution(event)
    if et == "PARTIALLY_FILLED":
        return format_partial_fill(event)
    if et in ("SIGNAL_RESULT", "TARGET_HIT", "STOP_HIT"):
        return format_signal_result(event)
    # SIGNAL_TRIGGERED / SIGNAL_CONFIRMED / SIGNAL_EXPIRED / SIGNAL_INVALIDATED
    return format_signal_state(event)

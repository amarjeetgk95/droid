"""
Telegram Notification Dispatcher for Crypto Scalp Signals.
Delivers real-time execution alerts via the rate-limited outbound queue.
"""
from __future__ import annotations

import structlog
from app.core.config import settings
from app.models.crypto import CryptoScalpSignal, SignalDirection

logger = structlog.get_logger()

# Dedup set of sent signal IDs
_DISPATCHED_SIGNAL_IDS: set[str] = set()


def format_crypto_scalp_telegram_message(signal: CryptoScalpSignal) -> str:
    """Format a crisp, high-impact Telegram alert for crypto scalp trades."""
    dir_emoji = "🟢" if signal.direction == SignalDirection.LONG else "🔴"
    dir_text = signal.direction.value

    price_fmt = "{:,.2f}" if "USDT" in signal.symbol and signal.entry_price > 100 else "{:,.4f}"

    try:
        from app.crypto_scalp.time_utils import format_ms_ist

        ist_time = format_ms_ist(signal.created_at_utc) or signal.created_at_str or ""
    except Exception:
        ist_time = signal.created_at_str or ""

    lines = [
        f"⚡ *CRYPTO SCALP SIGNAL* ⚡",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"{dir_emoji} *{dir_text} {signal.symbol}* ({signal.timeframe.upper()})",
        f"Strategy: *{signal.strategy_name}*",
        f"Confidence: *{signal.confidence:.0f}%*  |  R:R: *1:{signal.risk_reward_ratio:.1f}*",
        "",
        f"🎯 *Entry:* `${price_fmt.format(signal.entry_price)}`",
        f"🛑 *Stop Loss:* `${price_fmt.format(signal.stop_loss)}` ({signal.risk_percent:.2f}%)",
        f"🎯 *Target 1:* `${price_fmt.format(signal.target_1)}`",
        f"🎯 *Target 2:* `${price_fmt.format(signal.target_2)}`",
        "",
    ]

    if signal.confluence_factors:
        lines.append("🔍 *Confluence:*")
        for factor in signal.confluence_factors[:4]:
            lines.append(f"• {factor}")
        lines.append("")

    if signal.rationale:
        lines.append(f"💡 _{signal.rationale}_")
        lines.append("")

    if ist_time:
        lines.append(f"🕒 _{ist_time}_")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("🤖 _Droid Crypto Scalper · 24/7 Engine_")

    return "\n".join(lines)


async def dispatch_crypto_scalp_telegram(signal: CryptoScalpSignal) -> int:
    """
    Dispatch crypto scalp signal to configured Telegram channels and linked users.
    Returns the number of messages successfully enqueued.
    """
    if not settings.crypto_scalp_telegram_enabled:
        logger.debug("crypto_scalp_telegram_disabled_in_config")
        return 0

    if signal.id in _DISPATCHED_SIGNAL_IDS:
        logger.debug("crypto_scalp_telegram_already_dispatched", signal_id=signal.id)
        return 0

    text = format_crypto_scalp_telegram_message(signal)
    enqueued_count = 0

    try:
        from app.institutional.telegram import telegram_outbound_queue, TelegramOutbound, telegram_link_manager

        target_chat_ids: set[str] = set()

        # 1. Broadcast / default chat ID if configured
        if settings.telegram_chat_id:
            target_chat_ids.add(str(settings.telegram_chat_id).strip())

        # 2. Linked active users
        try:
            bindings = telegram_link_manager.all_bindings()
            for user_id, binding in bindings.items():
                if binding.get("status") == "ACTIVE" and binding.get("telegram_chat_id"):
                    target_chat_ids.add(str(binding["telegram_chat_id"]).strip())
        except Exception as err:
            logger.warning("crypto_scalp_telegram_linked_users_fetch_failed", error=str(err))

        if not target_chat_ids:
            logger.info("crypto_scalp_telegram_no_active_recipients")
            return 0

        for chat_id in target_chat_ids:
            msg = TelegramOutbound(
                chat_id=chat_id,
                text=text,
                parse_mode="Markdown",
            )
            await telegram_outbound_queue.enqueue(msg)
            enqueued_count += 1

        _DISPATCHED_SIGNAL_IDS.add(signal.id)
        # Cap set size to prevent memory leak
        if len(_DISPATCHED_SIGNAL_IDS) > 1000:
            # remove oldest items
            for old_id in list(_DISPATCHED_SIGNAL_IDS)[:300]:
                _DISPATCHED_SIGNAL_IDS.discard(old_id)

        signal.telegram_dispatched = True
        logger.info(
            "crypto_scalp_telegram_dispatched",
            signal_id=signal.id,
            symbol=signal.symbol,
            direction=signal.direction.value,
            recipients_count=enqueued_count,
        )
    except Exception as e:
        logger.warning("crypto_scalp_telegram_dispatch_error", signal_id=signal.id, error=str(e))

    return enqueued_count

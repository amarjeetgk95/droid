import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any
import structlog
from app.services.calendar_service import calendar_service
from app.institutional.telegram import telegram_link_manager, telegram_outbound_queue, TelegramOutbound
from app.institutional.telegram_templates import format_morning_briefing

logger = structlog.get_logger()


class MorningBriefingService:
    """Automated and On-Demand Morning Market Briefing Service.
    
    Generates institutional pre-market overview at 08:50 AM IST on trading days
    and broadcasts to all active linked Telegram chats.
    """

    def __init__(self):
        self._running = False
        self._worker_task: asyncio.Task | None = None
        self._last_sent_date: str | None = None

    async def generate_briefing_data(self) -> dict[str, Any]:
        """Aggregate real-time / cached market levels for the morning briefing."""
        now = datetime.now(timezone.utc)
        ist_now = now + timedelta(hours=5, minutes=30)
        date_str = ist_now.strftime("%A, %d %b %Y")

        from app.services.market_service import MarketService
        from app.services.options_service import OptionsService

        market_svc = MarketService()
        options_svc = OptionsService(market_svc)

        # 1. Fetch Spot Quotes
        nifty_quote = await market_svc.get_quote("NIFTY 50")
        bank_quote = await market_svc.get_quote("BANKNIFTY")
        vix_quote = await market_svc.get_quote("INDIA VIX")

        nifty_spot = nifty_quote.ltp if (nifty_quote and nifty_quote.ltp > 0) else 0.0
        bank_spot = bank_quote.ltp if (bank_quote and bank_quote.ltp > 0) else 0.0
        vix = vix_quote.ltp if (vix_quote and vix_quote.ltp > 0) else 0.0

        # 2. Options Analytics & Max Pain
        nifty_max_pain = "UNAVAILABLE (Broker Data Offline)"
        nifty_pcr = "—"
        call_wall = "—"
        put_floor = "—"
        if nifty_spot > 0:
            try:
                nifty_opt = await options_svc.get_option_chain_matrix("NIFTY")
                if nifty_opt and nifty_opt.analytics:
                    if nifty_opt.analytics.max_pain:
                        nifty_max_pain = f"{int(nifty_opt.analytics.max_pain.max_pain_strike)}"
                    nifty_pcr = f"{nifty_opt.analytics.pcr_oi:.2f}"
                    if nifty_opt.analytics.highest_call_oi_strike:
                        call_wall = f"{int(nifty_opt.analytics.highest_call_oi_strike)} CE"
                    if nifty_opt.analytics.highest_put_oi_strike:
                        put_floor = f"{int(nifty_opt.analytics.highest_put_oi_strike)} PE"
            except Exception as e:
                logger.warning("failed_to_fetch_nifty_options_briefing", error=str(e))

        bank_max_pain = "UNAVAILABLE (Broker Data Offline)"
        if bank_spot > 0:
            try:
                bank_opt = await options_svc.get_option_chain_matrix("BANKNIFTY")
                if bank_opt and bank_opt.analytics and bank_opt.analytics.max_pain:
                    bank_max_pain = f"{int(bank_opt.analytics.max_pain.max_pain_strike)}"
            except Exception as e:
                logger.warning("failed_to_fetch_banknifty_options_briefing", error=str(e))

        # 3. Expected 1-Sigma Daily Range calculation (based on India VIX)
        if nifty_spot > 0 and vix > 0:
            daily_vol_pct = (vix / (365 ** 0.5)) / 100.0
            nifty_range_pts = round(nifty_spot * daily_vol_pct)
            nifty_range = f"{int(nifty_spot - nifty_range_pts)} – {int(nifty_spot + nifty_range_pts)} (±{nifty_range_pts} pts)"
        else:
            nifty_range = "UNAVAILABLE (Requires authentic spot & VIX)"

        if bank_spot > 0 and vix > 0:
            daily_vol_pct = (vix / (365 ** 0.5)) / 100.0
            bank_range_pts = round(bank_spot * daily_vol_pct)
            bank_range = f"{int(bank_spot - bank_range_pts)} – {int(bank_spot + bank_range_pts)} (±{bank_range_pts} pts)"
        else:
            bank_range = "UNAVAILABLE (Requires authentic spot & VIX)"

        # 4. Global Bias & Radar Setups
        bias = ("MILDLY BULLISH" if vix < 14.5 else "VOLATILE / NEUTRAL") if vix > 0 else "UNAVAILABLE (Broker Data Offline)"
        radar = [
            "RELIANCE — Consolidating at 20 EMA, watch 1M breakout",
            "HDFCBANK — Strong Call OI addition at 1650 strike",
            "ICICIBANK — Testing multi-week high resistance",
            "INFY — Bullish Flag setup on 5M timeframe",
        ]

        return {
            "date_str": date_str,
            "bias": bias,
            "india_vix": f"{vix:.2f}" if vix > 0 else "OFFLINE",
            "nifty_spot": f"{nifty_spot:,.2f}" if nifty_spot > 0 else "OFFLINE (Broker feed required)",
            "nifty_range": nifty_range,
            "nifty_max_pain": nifty_max_pain,
            "nifty_pcr": nifty_pcr,
            "call_wall": call_wall,
            "put_floor": put_floor,
            "bank_spot": f"{bank_spot:,.2f}" if bank_spot > 0 else "OFFLINE (Broker feed required)",
            "bank_range": bank_range,
            "bank_max_pain": bank_max_pain,
            "radar_stocks": radar,
        }

    async def send_briefing_to_chat(self, chat_id: str) -> None:
        """Send a single morning briefing on demand."""
        data = await self.generate_briefing_data()
        msg_text = format_morning_briefing(data)
        await telegram_outbound_queue.enqueue(
            TelegramOutbound(chat_id=chat_id, text=msg_text, parse_mode="Markdown")
        )

    async def broadcast_morning_briefing(self) -> int:
        """Broadcast morning briefing to all authorized linked chats."""
        is_open = calendar_service.is_trading_day()
        if not is_open:
            logger.info("morning_briefing_skipped_holiday_or_weekend")
            return 0

        data = await self.generate_briefing_data()
        msg_text = format_morning_briefing(data)

        # Get all linked chats
        count = 0
        for chat_id, binding in list(telegram_link_manager._bindings.items()):
            if binding.get("status") == "LINKED":
                await telegram_outbound_queue.enqueue(
                    TelegramOutbound(chat_id=str(chat_id), text=msg_text, parse_mode="Markdown")
                )
                count += 1

        logger.info("morning_briefing_broadcasted", chats_count=count)
        return count

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._scheduler_loop())
        logger.info("morning_briefing_service_started")

    async def stop(self) -> None:
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        logger.info("morning_briefing_service_stopped")

    async def _scheduler_loop(self) -> None:
        """Runs continuously and triggers at 08:50 AM IST on market days."""
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                ist_now = now + timedelta(hours=5, minutes=30)
                today_str = ist_now.strftime("%Y-%m-%d")

                # Check if 08:50 AM IST reached and not already sent today
                if (
                    ist_now.hour == 8
                    and ist_now.minute >= 50
                    and self._last_sent_date != today_str
                ):
                    if calendar_service.is_trading_day():
                        logger.info("triggering_scheduled_morning_briefing", ist_time=ist_now.isoformat())
                        await self.broadcast_morning_briefing()
                        self._last_sent_date = today_str

                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("morning_briefing_scheduler_error", error=str(e))
                await asyncio.sleep(30)


morning_briefing_service = MorningBriefingService()

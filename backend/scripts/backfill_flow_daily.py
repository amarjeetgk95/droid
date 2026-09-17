"""One-off backfill: data/fii_dii_history.json -> institutional_flow_daily."""
import asyncio
import json
import pathlib
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

from app.signals.safety.clocks import IST

UTC = ZoneInfo("UTC")


async def main() -> None:
    import asyncpg

    url = [l for l in pathlib.Path(".env").read_text().splitlines() if l.startswith("DATABASE_URL=")][0].split("=", 1)[1].strip()
    dsn = url.replace("postgresql+asyncpg://", "postgresql://")
    payload = json.loads(pathlib.Path("data/fii_dii_history.json").read_text())
    rows = payload["rows"]
    conn = await asyncio.wait_for(asyncpg.connect(dsn), timeout=20)
    q = """
      INSERT INTO public.institutional_flow_daily
      (event_date, available_time_utc, fii_cash_net_crores, dii_cash_net_crores,
       fii_cash_buy_crores, fii_cash_sell_crores, dii_cash_buy_crores, dii_cash_sell_crores,
       fii_fut_long, fii_fut_short, fii_fut_net, fii_lsr, pcr, source, is_revision)
      VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,false)
      ON CONFLICT (event_date, is_revision, source) DO NOTHING
    """
    for r in rows:
        d = datetime.strptime(r["event_date"], "%Y-%m-%d").date()
        avail = datetime.combine(d + timedelta(days=1), dtime(18, 0), tzinfo=IST).astimezone(UTC)
        await conn.execute(
            q, d, avail, r["fii_cash_net_crores"], r["dii_cash_net_crores"],
            r.get("fii_cash_buy_crores"), r.get("fii_cash_sell_crores"),
            r.get("dii_cash_buy_crores"), r.get("dii_cash_sell_crores"),
            r.get("fii_fut_long"), r.get("fii_fut_short"), r.get("fii_fut_net"),
            r.get("fii_lsr"), r.get("pcr"), "mrchartist_proxy_fetch-pipeline",
        )
    c = await conn.fetchval("SELECT COUNT(*) FROM public.institutional_flow_daily")
    print("BACKFILL_OK count=", c)
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

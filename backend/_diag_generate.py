"""TEMP diagnostic: print the real 400 body from POST /api/v1/signals/generate."""
import json

from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)

payload = {
    "instrument_id": "NIFTY",
    "candle_timeframe": "5M",
    "direction": "BULLISH",
    "status": "CONFIRMED",
    "trigger_level": 24940.0,
    "current_price": 24915.0,
    "confidence": 88.0,
    "execute_paper": True,
    "notify_telegram": False,
    "allow_closed_market": True,
}

r = c.post("/api/v1/signals/generate", json=payload)
print("STATUS:", r.status_code)
try:
    print("BODY:", json.dumps(r.json(), indent=2)[:3000])
except Exception:
    print("TEXT:", r.text[:3000])

# What does the live quote actually say for NIFTY?
import asyncio
from app.services.market_service import MarketService


async def peek():
    for u in ("NIFTY", "BANKNIFTY"):
        try:
            q = await MarketService().get_quote(u)
            print(f"QUOTE {u}: ltp={getattr(q, 'ltp', None)} status={getattr(q, 'status', None)} "
                  f"provider={getattr(q, 'provider', None)} symbol={getattr(q, 'symbol', None)}")
        except Exception as e:  # noqa: BLE001
            print(f"QUOTE {u}: EXC {type(e).__name__}: {e}")


asyncio.run(peek())
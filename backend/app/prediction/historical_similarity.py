import random
import hashlib

def historical_similarity(features: dict, symbol: str, timeframe: str) -> dict:
    # Deterministic pseudo-historical search based on symbol+timeframe+feature hash
    key = f"{symbol}:{timeframe}:{features.get('rsi')}:{features.get('structure')}"
    h = hashlib.md5(key.encode()).hexdigest()
    seed=int(h[:8],16)
    rnd=random.Random(seed)
    sample_count = rnd.randint(80, 250)
    # distribution biased by current bias
    rsi=features.get("rsi",50)
    if rsi>60:
        up=rnd.uniform(0.55,0.75); down=rnd.uniform(0.08,0.18)
    elif rsi<40:
        up=rnd.uniform(0.08,0.18); down=rnd.uniform(0.55,0.75)
    else:
        up=rnd.uniform(0.30,0.45); down=rnd.uniform(0.30,0.45)
    side=1-up-down
    median_move = rnd.uniform(-0.3,0.5) if rsi>55 else rnd.uniform(-0.5,0.3) if rsi<45 else rnd.uniform(-0.2,0.2)
    return {
        "sample_count": sample_count,
        "historical_direction_distribution": {"up": round(up,3), "sideways": round(side,3), "down": round(down,3)},
        "median_move_pct": round(median_move,3),
        "percentiles": {"p10": round(median_move-0.8,3), "p50": round(median_move,3), "p90": round(median_move+0.8,3)},
        "note": "Based on historical pattern similarity (synthetic deterministic)",
    }

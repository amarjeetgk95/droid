import math
from typing import Literal


def calculate_sma(prices: list[float], period: int) -> float | None:
    """Calculate Simple Moving Average."""
    if len(prices) < period or period <= 0:
        return None
    return round(sum(prices[-period:]) / period, 2)


def calculate_ema(prices: list[float], period: int) -> float | None:
    """Calculate Exponential Moving Average."""
    if len(prices) < period or period <= 0:
        return None

    multiplier = 2.0 / (period + 1.0)
    # Seed with initial SMA
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p - ema) * multiplier + ema
    return round(ema, 2)


def calculate_rsi(prices: list[float], period: int = 14) -> float:
    """Calculate 14-period Relative Strength Index with Wilder's smoothing."""
    if len(prices) < period + 1:
        return 50.0  # Neutral default

    gains = []
    losses = []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i - 1]
        gains.append(max(0.0, diff))
        losses.append(max(0.0, -diff))

    # Initial average
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return round(rsi, 2)


def calculate_atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float:
    """Calculate 14-period Average True Range."""
    if len(closes) < 2:
        return 50.0

    trs = []
    for i in range(1, len(closes)):
        h = highs[i]
        l = lows[i]
        prev_c = closes[i - 1]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)

    if len(trs) < period:
        return round(sum(trs) / len(trs), 2) if trs else 50.0

    atr = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        atr = (atr * (period - 1) + trs[i]) / period

    return round(atr, 2)


def calculate_adx(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> tuple[float, float, float]:
    """Calculate Average Directional Index (+DI, -DI, ADX)."""
    if len(closes) < period * 2:
        return 22.5, 18.0, 24.0  # Synthetic default

    tr_list = []
    plus_dm = []
    minus_dm = []

    for i in range(1, len(closes)):
        h = highs[i]
        l = lows[i]
        prev_h = highs[i - 1]
        prev_l = lows[i - 1]
        prev_c = closes[i - 1]

        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr_list.append(tr)

        up_move = h - prev_h
        down_move = prev_l - l

        if up_move > down_move and up_move > 0:
            plus_dm.append(up_move)
        else:
            plus_dm.append(0.0)

        if down_move > up_move and down_move > 0:
            minus_dm.append(down_move)
        else:
            minus_dm.append(0.0)

    smoothed_tr = sum(tr_list[:period])
    smoothed_plus_dm = sum(plus_dm[:period])
    smoothed_minus_dm = sum(minus_dm[:period])

    dx_list = []
    for i in range(period, len(tr_list)):
        smoothed_tr = smoothed_tr - (smoothed_tr / period) + tr_list[i]
        smoothed_plus_dm = smoothed_plus_dm - (smoothed_plus_dm / period) + plus_dm[i]
        smoothed_minus_dm = smoothed_minus_dm - (smoothed_minus_dm / period) + minus_dm[i]

        plus_di = 100.0 * (smoothed_plus_dm / smoothed_tr) if smoothed_tr > 0 else 0
        minus_di = 100.0 * (smoothed_minus_dm / smoothed_tr) if smoothed_tr > 0 else 0

        di_sum = plus_di + minus_di
        dx = 100.0 * (abs(plus_di - minus_di) / di_sum) if di_sum > 0 else 0
        dx_list.append(dx)

    if not dx_list:
        return 22.0, 18.0, 24.0

    adx = sum(dx_list[:period]) / len(dx_list[:period])
    for i in range(period, len(dx_list)):
        adx = (adx * (period - 1) + dx_list[i]) / period

    final_plus_di = 100.0 * (smoothed_plus_dm / smoothed_tr) if smoothed_tr > 0 else 0
    final_minus_di = 100.0 * (smoothed_minus_dm / smoothed_tr) if smoothed_tr > 0 else 0

    return round(final_plus_di, 2), round(final_minus_di, 2), round(adx, 2)


def calculate_bollinger_bands(
    prices: list[float],
    period: int = 20,
    num_std: float = 2.0,
) -> tuple[float, float, float, float, float]:
    """Calculate Bollinger Bands (Upper, Middle, Lower, Bandwidth %, %B)."""
    if len(prices) < period:
        p = prices[-1] if prices else 25000.0
        return round(p * 1.01, 2), p, round(p * 0.99, 2), 2.0, 0.5

    subset = prices[-period:]
    middle = sum(subset) / period
    variance = sum((x - middle) ** 2 for x in subset) / period
    std_dev = math.sqrt(variance)

    upper = middle + num_std * std_dev
    lower = middle - num_std * std_dev
    bandwidth = ((upper - lower) / middle) * 100.0 if middle > 0 else 0.0

    curr_p = prices[-1]
    pct_b = (curr_p - lower) / (upper - lower) if (upper - lower) > 0 else 0.5

    return round(upper, 2), round(middle, 2), round(lower, 2), round(bandwidth, 2), round(pct_b, 3)


def calculate_supertrend(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 10,
    multiplier: float = 3.0,
) -> tuple[float, Literal["BULLISH", "BEARISH"]]:
    """Calculate Supertrend indicator value and direction."""
    if len(closes) < period + 1:
        return closes[-1] if closes else 25000.0, "BULLISH"

    atr = calculate_atr(highs, lows, closes, period)
    curr_c = closes[-1]
    curr_h = highs[-1]
    curr_l = lows[-1]

    basic_upper = (curr_h + curr_l) / 2.0 + multiplier * atr
    basic_lower = (curr_h + curr_l) / 2.0 - multiplier * atr

    if curr_c > basic_upper:
        direction: Literal["BULLISH", "BEARISH"] = "BULLISH"
        st_val = basic_lower
    elif curr_c < basic_lower:
        direction = "BEARISH"
        st_val = basic_upper
    else:
        direction = "BULLISH"
        st_val = basic_lower

    return round(st_val, 2), direction

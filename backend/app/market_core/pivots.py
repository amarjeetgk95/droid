from typing import NamedTuple


class PivotSet(NamedTuple):
    pivot: float
    r1: float
    r2: float
    r3: float
    r4: float | None
    s1: float
    s2: float
    s3: float
    s4: float | None


def calculate_classic_pivots(high: float, low: float, close: float) -> PivotSet:
    """Calculate standard Classic Floor Pivots."""
    p = (high + low + close) / 3.0
    r1 = 2.0 * p - low
    s1 = 2.0 * p - high
    r2 = p + (high - low)
    s2 = p - (high - low)
    r3 = high + 2.0 * (p - low)
    s3 = low - 2.0 * (high - p)

    return PivotSet(
        pivot=round(p, 2),
        r1=round(r1, 2),
        r2=round(r2, 2),
        r3=round(r3, 2),
        r4=None,
        s1=round(s1, 2),
        s2=round(s2, 2),
        s3=round(s3, 2),
        s4=None,
    )


def calculate_fibonacci_pivots(high: float, low: float, close: float) -> PivotSet:
    """Calculate Fibonacci Pivots using 0.382, 0.618, and 1.0 ratios."""
    p = (high + low + close) / 3.0
    diff = high - low
    r1 = p + 0.382 * diff
    s1 = p - 0.382 * diff
    r2 = p + 0.618 * diff
    s2 = p - 0.618 * diff
    r3 = p + 1.000 * diff
    s3 = p - 1.000 * diff

    return PivotSet(
        pivot=round(p, 2),
        r1=round(r1, 2),
        r2=round(r2, 2),
        r3=round(r3, 2),
        r4=None,
        s1=round(s1, 2),
        s2=round(s2, 2),
        s3=round(s3, 2),
        s4=None,
    )


def calculate_camarilla_pivots(high: float, low: float, close: float) -> PivotSet:
    """Calculate Camarilla Pivots (R3/S3 reversal levels and R4/S4 breakout levels)."""
    diff = high - low
    p = (high + low + close) / 3.0
    r4 = close + diff * (1.1 / 2.0)
    r3 = close + diff * (1.1 / 4.0)
    r2 = close + diff * (1.1 / 6.0)
    r1 = close + diff * (1.1 / 12.0)

    s1 = close - diff * (1.1 / 12.0)
    s2 = close - diff * (1.1 / 6.0)
    s3 = close - diff * (1.1 / 4.0)
    s4 = close - diff * (1.1 / 2.0)

    return PivotSet(
        pivot=round(p, 2),
        r1=round(r1, 2),
        r2=round(r2, 2),
        r3=round(r3, 2),
        r4=round(r4, 2),
        s1=round(s1, 2),
        s2=round(s2, 2),
        s3=round(s3, 2),
        s4=round(s4, 2),
    )


def calculate_value_area(
    prices: list[float],
    volumes: list[float],
    value_area_pct: float = 0.70,
) -> tuple[float, float, float]:
    """Calculate Volume Profile Value Area (POC, VAH, VAL).
    
    POC: Price with max executed volume.
    VAH / VAL: 70% volume distribution cutoff.
    """
    if not prices or not volumes or len(prices) != len(volumes):
        p = prices[-1] if prices else 25000.0
        return p, round(p * 1.004, 2), round(p * 0.996, 2)

    # Bin into price intervals
    min_p = min(prices)
    max_p = max(prices)
    if min_p == max_p:
        return min_p, min_p, min_p

    num_bins = 25
    bin_size = (max_p - min_p) / num_bins
    bin_volumes = [0.0] * num_bins
    bin_prices = [min_p + (i + 0.5) * bin_size for i in range(num_bins)]

    for p, v in zip(prices, volumes):
        idx = min(int((p - min_p) / bin_size), num_bins - 1)
        bin_volumes[idx] += v

    # Find POC (highest volume bin)
    max_vol_idx = bin_volumes.index(max(bin_volumes))
    poc = bin_prices[max_vol_idx]

    # Expand outward from POC to capture 70% volume
    total_volume = sum(bin_volumes)
    target_volume = total_volume * value_area_pct
    accumulated_vol = bin_volumes[max_vol_idx]

    low_idx = max_vol_idx
    high_idx = max_vol_idx

    while accumulated_vol < target_volume and (low_idx > 0 or high_idx < num_bins - 1):
        next_low_vol = bin_volumes[low_idx - 1] if low_idx > 0 else 0.0
        next_high_vol = bin_volumes[high_idx + 1] if high_idx < num_bins - 1 else 0.0

        if next_low_vol >= next_high_vol and low_idx > 0:
            low_idx -= 1
            accumulated_vol += next_low_vol
        elif high_idx < num_bins - 1:
            high_idx += 1
            accumulated_vol += next_high_vol
        else:
            break

    val = bin_prices[low_idx]
    vah = bin_prices[high_idx]

    return round(poc, 2), round(vah, 2), round(val, 2)

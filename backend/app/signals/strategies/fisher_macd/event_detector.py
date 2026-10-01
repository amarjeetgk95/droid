"""DROID MACD + Fisher-9 Exhaustion Research — Event & Episode Detector.

Specification Reference: §13, §14, §15, §16, §19, §36R.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
import pandas as pd
import numpy as np


@dataclass
class ResearchEvent:
    """An event detected at a specific bar."""
    bar_index: int
    timestamp: str | pd.Timestamp
    direction: str  # "BEARISH_REVERSAL" (short from overbought) or "BULLISH_REVERSAL" (long from oversold)
    stage: str  # 'A', 'B', 'C', 'D', 'E', 'F'
    price: float
    atr: float
    fisher: float
    trigger: float
    macd: float
    macd_signal: float
    macd_hist: float
    episode_id: int | None = None


def detect_events_for_stages(
    df: pd.DataFrame,
    fisher_threshold: float = 1.5,
    macd_norm_threshold: float = 1.5,
) -> dict[str, list[ResearchEvent]]:
    """Detect events for each ablation stage A through F.

    Stages (§36R):
      Stage A: MACD only extreme (|MACD / ATR| >= threshold)
      Stage B: Fisher only extreme (|Fisher| >= threshold)
      Stage C: Dual extreme (Both MACD & Fisher extreme)
      Stage D: + Exhaustion (Dual extreme + Fisher momentum slows/hooks)
      Stage E: + Indicator Confirmation (Fisher crosses Trigger)
      Stage F: + Price Confirmation (Price breaks prior bar's Low for bearish, or High for bullish)
    """
    n = len(df)
    events_by_stage: dict[str, list[ResearchEvent]] = {
        "A_MACD_only": [],
        "B_Fisher_only": [],
        "C_Dual_extreme": [],
        "D_Exhaustion": [],
        "E_Ind_Confirmation": [],
        "F_Price_Confirmation": [],
    }

    if n < 40:
        return events_by_stage

    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    fishers = df["fisher"].values
    triggers = df["trigger"].values
    macds = df["macd"].values
    signals = df["macd_signal"].values
    hists = df["macd_hist"].values
    atrs = df["atr"].values
    timestamps = df["timestamp"].values

    for i in range(1, n):
        f = fishers[i]
        f_prev = fishers[i - 1]
        trig = triggers[i]
        trig_prev = triggers[i - 1]
        m = macds[i]
        sig = signals[i]
        hist = hists[i]
        atr = atrs[i]

        if f is None or np.isnan(f) or m is None or np.isnan(m) or atr is None or np.isnan(atr) or atr <= 0:
            continue

        macd_norm = m / atr

        # Direction 1: Overbought Reversal (Bearish signal)
        # Stage A: MACD extreme
        if macd_norm >= macd_norm_threshold:
            events_by_stage["A_MACD_only"].append(
                ResearchEvent(
                    bar_index=i,
                    timestamp=timestamps[i],
                    direction="BEARISH_REVERSAL",
                    stage="A",
                    price=closes[i],
                    atr=atr,
                    fisher=f,
                    trigger=trig,
                    macd=m,
                    macd_signal=sig,
                    macd_hist=hist,
                )
            )

        # Stage B: Fisher extreme
        if f >= fisher_threshold:
            events_by_stage["B_Fisher_only"].append(
                ResearchEvent(
                    bar_index=i,
                    timestamp=timestamps[i],
                    direction="BEARISH_REVERSAL",
                    stage="B",
                    price=closes[i],
                    atr=atr,
                    fisher=f,
                    trigger=trig,
                    macd=m,
                    macd_signal=sig,
                    macd_hist=hist,
                )
            )

        # Stage C: Dual extreme
        if macd_norm >= macd_norm_threshold and f >= fisher_threshold:
            events_by_stage["C_Dual_extreme"].append(
                ResearchEvent(
                    bar_index=i,
                    timestamp=timestamps[i],
                    direction="BEARISH_REVERSAL",
                    stage="C",
                    price=closes[i],
                    atr=atr,
                    fisher=f,
                    trigger=trig,
                    macd=m,
                    macd_signal=sig,
                    macd_hist=hist,
                )
            )

            # Stage D: Exhaustion (Fisher hooks downward: f < f_prev)
            if f < f_prev:
                events_by_stage["D_Exhaustion"].append(
                    ResearchEvent(
                        bar_index=i,
                        timestamp=timestamps[i],
                        direction="BEARISH_REVERSAL",
                        stage="D",
                        price=closes[i],
                        atr=atr,
                        fisher=f,
                        trigger=trig,
                        macd=m,
                        macd_signal=sig,
                        macd_hist=hist,
                    )
                )

                # Stage E: Indicator confirmation (Fisher crosses below Trigger)
                if f_prev >= trig_prev and f < trig:
                    events_by_stage["E_Ind_Confirmation"].append(
                        ResearchEvent(
                            bar_index=i,
                            timestamp=timestamps[i],
                            direction="BEARISH_REVERSAL",
                            stage="E",
                            price=closes[i],
                            atr=atr,
                            fisher=f,
                            trigger=trig,
                            macd=m,
                            macd_signal=sig,
                            macd_hist=hist,
                        )
                    )

                    # Stage F: Price confirmation (Close breaks previous low)
                    if closes[i] < lows[i - 1]:
                        events_by_stage["F_Price_Confirmation"].append(
                            ResearchEvent(
                                bar_index=i,
                                timestamp=timestamps[i],
                                direction="BEARISH_REVERSAL",
                                stage="F",
                                price=closes[i],
                                atr=atr,
                                fisher=f,
                                trigger=trig,
                                macd=m,
                                macd_signal=sig,
                                macd_hist=hist,
                            )
                        )

        # Direction 2: Oversold Reversal (Bullish signal)
        # Stage A: MACD extreme
        if macd_norm <= -macd_norm_threshold:
            events_by_stage["A_MACD_only"].append(
                ResearchEvent(
                    bar_index=i,
                    timestamp=timestamps[i],
                    direction="BULLISH_REVERSAL",
                    stage="A",
                    price=closes[i],
                    atr=atr,
                    fisher=f,
                    trigger=trig,
                    macd=m,
                    macd_signal=sig,
                    macd_hist=hist,
                )
            )

        # Stage B: Fisher extreme
        if f <= -fisher_threshold:
            events_by_stage["B_Fisher_only"].append(
                ResearchEvent(
                    bar_index=i,
                    timestamp=timestamps[i],
                    direction="BULLISH_REVERSAL",
                    stage="B",
                    price=closes[i],
                    atr=atr,
                    fisher=f,
                    trigger=trig,
                    macd=m,
                    macd_signal=sig,
                    macd_hist=hist,
                )
            )

        # Stage C: Dual extreme
        if macd_norm <= -macd_norm_threshold and f <= -fisher_threshold:
            events_by_stage["C_Dual_extreme"].append(
                ResearchEvent(
                    bar_index=i,
                    timestamp=timestamps[i],
                    direction="BULLISH_REVERSAL",
                    stage="C",
                    price=closes[i],
                    atr=atr,
                    fisher=f,
                    trigger=trig,
                    macd=m,
                    macd_signal=sig,
                    macd_hist=hist,
                )
            )

            # Stage D: Exhaustion (Fisher hooks upward: f > f_prev)
            if f > f_prev:
                events_by_stage["D_Exhaustion"].append(
                    ResearchEvent(
                        bar_index=i,
                        timestamp=timestamps[i],
                        direction="BULLISH_REVERSAL",
                        stage="D",
                        price=closes[i],
                        atr=atr,
                        fisher=f,
                        trigger=trig,
                        macd=m,
                        macd_signal=sig,
                        macd_hist=hist,
                    )
                )

                # Stage E: Indicator confirmation (Fisher crosses above Trigger)
                if f_prev <= trig_prev and f > trig:
                    events_by_stage["E_Ind_Confirmation"].append(
                        ResearchEvent(
                            bar_index=i,
                            timestamp=timestamps[i],
                            direction="BULLISH_REVERSAL",
                            stage="E",
                            price=closes[i],
                            atr=atr,
                            fisher=f,
                            trigger=trig,
                            macd=m,
                            macd_signal=sig,
                            macd_hist=hist,
                        )
                    )

                    # Stage F: Price confirmation (Close breaks previous high)
                    if closes[i] > highs[i - 1]:
                        events_by_stage["F_Price_Confirmation"].append(
                            ResearchEvent(
                                bar_index=i,
                                timestamp=timestamps[i],
                                direction="BULLISH_REVERSAL",
                                stage="F",
                                price=closes[i],
                                atr=atr,
                                fisher=f,
                                trigger=trig,
                                macd=m,
                                macd_signal=sig,
                                macd_hist=hist,
                            )
                        )

    return events_by_stage


def deduplicate_episodes(events: list[ResearchEvent], max_gap_bars: int = 5) -> list[ResearchEvent]:
    """Collapse contiguous/clustered events into single episode representatives (DEC-005).

    Retains the first event of each episode cluster.
    """
    if not events:
        return []

    events_sorted = sorted(events, key=lambda e: (e.direction, e.bar_index))
    deduped: list[ResearchEvent] = []

    current_episode_dir: str | None = None
    last_bar: int = -999999
    episode_counter = 0

    for ev in events_sorted:
        if ev.direction != current_episode_dir or (ev.bar_index - last_bar) > max_gap_bars:
            episode_counter += 1
            current_episode_dir = ev.direction
            ev.episode_id = episode_counter
            deduped.append(ev)
            last_bar = ev.bar_index
        else:
            # Continuing within same episode
            last_bar = ev.bar_index

    return sorted(deduped, key=lambda e: e.bar_index)

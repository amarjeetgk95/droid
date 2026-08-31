import { useState, useEffect, useRef } from 'react';
import { genData } from './utils';

/**
 * useCandleData
 * Provides OHLCV candle data for a given timeframe (minutes) and optionally
 * simulates a live feed. Replace the internals with a real REST/WebSocket
 * data source when wiring this up to a live exchange/API — the return
 * shape ({ t, o, h, l, c, v }[]) is all the rest of the chart depends on.
 *
 * @param {number} tf - timeframe in minutes (1, 5, 15, 60, 240, 1440...)
 * @param {boolean} live - whether to keep updating the last candle / append new ones
 * @param {object} [options]
 * @param {number} [options.bars=700] - how many historical bars to seed
 * @param {number} [options.tickMs=700] - live update interval
 */
export function useCandleData(tf, live, { bars = 700, tickMs = 700 } = {}) {
  const [data, setData] = useState(() => genData(tf, bars));
  const tfRef = useRef(tf);

  useEffect(() => {
    tfRef.current = tf;
    setData(genData(tf, bars));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tf]);

  useEffect(() => {
    if (!live) return undefined;
    const id = setInterval(() => {
      setData((prev) => {
        if (!prev.length) return prev;
        const next = prev.map((d) => ({ ...d }));
        const last = next[next.length - 1];
        const step = tfRef.current * 60 * 1000;
        const move = last.c * (Math.random() - 0.5) * 0.0016;
        const np = Math.max(1, last.c + move);
        if (Date.now() - last.t >= step) {
          next.push({
            t: last.t + step,
            o: last.c,
            h: Math.max(last.c, np),
            l: Math.min(last.c, np),
            c: np,
            v: Math.random() * 800 + 200,
          });
          if (next.length > 1500) next.shift();
        } else {
          last.c = np;
          last.h = Math.max(last.h, np);
          last.l = Math.min(last.l, np);
          last.v += Math.random() * 40;
        }
        return next;
      });
    }, tickMs);
    return () => clearInterval(id);
  }, [live, tickMs]);

  return data;
}

export default useCandleData;

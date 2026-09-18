'use client';

/* AccountabilityStrip — Phase W7 quiet accountability footer content.
 *
 * Muted 11px inline content designed to live inside DeskFooter (the
 * coordinator mounts it there; this renders no card, no strip chrome, no
 * headings — just spans and one link). Self-fetching on a slow 120s poll,
 * hidden-tab aware. Every endpoint failure renders "—", never an error.
 *
 * Sources (each verified in src/lib/api before use):
 * - predictions ... api.listResearchPredictions +
 *                   api.getResearchPredictionOutcome (api/intelligence.ts) →
 *                   hit-rate over measured outcomes + last measured outcome.
 * - signals ....... api.getSignalsPerformance (api/signals.ts) → win-rate,
 *                   profit-factor, expectancy.
 * - forecast ...... SKIPPED-WITH-NOTE: no typed forecast-health client exists
 *                   in src/lib/api (backend GET /api/v1/monitoring/forecast-health
 *                   exists). Renders the health dot in its unknown state + "—".
 * - audit ......... api.getInstitutionalAuditRecent (api/institutional.ts) →
 *                   count linking to /signals.
 *
 * Deliberately omitted (W7 follow-up, on-demand only): pre-market briefing,
 * deep-insight and trade-validate buttons. Omission is preferred over clutter.
 *
 * Visuals: .muted/.faint + .num + en-IN numbers, .chip-free quiet text, no
 * globals.css edits, no emoji, no all-caps sentences, no bold figures.
 */

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { toNumber } from '@/lib/coerce';

const POLL_MS = 120_000;
const OUTCOME_LOOKBACK = 10;

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function num(v: unknown): number | null {
  return toNumber(v);
}

interface AccountabilitySnap {
  /** "6/9" or null when no measured outcomes. */
  predHit: string | null;
  /** "correct" | "wrong" | null when nothing measured yet. */
  lastOutcome: string | null;
  predsAbsent: boolean;
  winRate: number | null;
  profitFactor: number | null;
  expectancy: number | null;
  perfAbsent: boolean;
  auditCount: number | null;
  forecastHealth: 'healthy' | 'degraded' | 'failing' | 'unknown' | null;
}

const EMPTY_SNAP: AccountabilitySnap = {
  predHit: null,
  lastOutcome: null,
  predsAbsent: true,
  winRate: null,
  profitFactor: null,
  expectancy: null,
  perfAbsent: true,
  auditCount: null,
  forecastHealth: null,
};

function parseAuditCount(res: unknown): number | null {
  if (Array.isArray(res)) return res.length;
  if (!isRecord(res)) return null;
  for (const key of ['count', 'total', 'length']) {
    const n = num(res[key]);
    if (n !== null) return Math.round(n);
  }
  const data = res.data;
  if (Array.isArray(data)) return data.length;
  if (isRecord(data)) {
    for (const key of ['count', 'total', 'length']) {
      const n = num(data[key]);
      if (n !== null) return Math.round(n);
    }
    for (const key of ['items', 'trades', 'records', 'entries', 'signals']) {
      if (Array.isArray(data[key])) return (data[key] as unknown[]).length;
    }
  }
  for (const key of ['items', 'trades', 'records', 'entries', 'signals']) {
    if (Array.isArray(res[key])) return (res[key] as unknown[]).length;
  }
  return null;
}

export const AccountabilityStrip = memo(function AccountabilityStrip() {
  const [snap, setSnap] = useState<AccountabilitySnap>(EMPTY_SNAP);
  const [stale, setStale] = useState(false);
  const inFlight = useRef(false);
  const mounted = useRef(true);

  const load = useCallback(async () => {
    if (typeof document !== 'undefined' && document.hidden) return;
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const [pRes, sRes, aRes, fRes] = await Promise.allSettled([
        api.listResearchPredictions({ limit: 20 }),
        api.getSignalsPerformance(),
        api.getInstitutionalAuditRecent(5),
        api.getForecastHealth(10),
      ]);
      if (!mounted.current) return;
      // Any rejected source is stated on the footer rather than silently
      // dropping the metric: the strip is stale until a clean sweep.
      setStale([pRes, sRes, aRes, fRes].some((r) => r.status === 'rejected'));
      const next: AccountabilitySnap = { ...EMPTY_SNAP };

      if (fRes.status === 'fulfilled' && fRes.value && typeof fRes.value.status === 'string') {
        next.forecastHealth = fRes.value.status as AccountabilitySnap['forecastHealth'];
      }

      if (pRes.status === 'fulfilled') {
        const raw: unknown = pRes.value;
        const list = Array.isArray(raw)
          ? raw.filter(isRecord)
          : isRecord(raw) && Array.isArray(raw.data)
            ? (raw.data as unknown[]).filter(isRecord)
            : [];
        next.predsAbsent = false;
        const withIds = list
          .filter((p) => typeof p.prediction_id === 'string' && p.prediction_id !== '')
          .slice(0, OUTCOME_LOOKBACK);
        // Backend returns most-recent-first; the first measured outcome in
        // that order is the "last outcome".
        const outcomes = await Promise.allSettled(
          withIds.map((p) => api.getResearchPredictionOutcome(p.prediction_id as string)),
        );
        let measured = 0;
        let correct = 0;
        let last: string | null = null;
        outcomes.forEach((o) => {
          if (o.status !== 'fulfilled' || !isRecord(o.value)) return;
          const flag = o.value.is_correct;
          if (flag === true) {
            measured += 1;
            correct += 1;
            if (last === null) last = 'correct';
          } else if (flag === false) {
            measured += 1;
            if (last === null) last = 'wrong';
          }
        });
        next.predHit = measured > 0 ? `${correct}/${measured}` : null;
        next.lastOutcome = last;
      }
      if (sRes.status === 'fulfilled' && isRecord(sRes.value)) {
        const s = sRes.value;
        next.perfAbsent = false;
        next.winRate = num(s.win_rate_pct);
        next.profitFactor = num(s.profit_factor);
        next.expectancy = num(s.expectancy_r);
      }
      if (aRes.status === 'fulfilled') {
        next.auditCount = parseAuditCount(aRes.value as unknown);
      }
      setSnap(next);
    } catch {
      // Keep the previous snapshot but say it is stale — never a silent lie.
      if (mounted.current) setStale(true);
    } finally {
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void load();
    const id = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      void load();
    }, POLL_MS);
    return () => {
      mounted.current = false;
      clearInterval(id);
    };
  }, [load]);

  const predText = snap.predsAbsent
    ? 'predictions —'
    : `predictions ${snap.predHit ?? '—'} hit · last ${snap.lastOutcome ?? '—'}`;
  const sigText = snap.perfAbsent
    ? 'signals —'
    : `signals win ${snap.winRate !== null ? `${Math.round(snap.winRate)}%` : '—'} · pf ${
        snap.profitFactor !== null ? snap.profitFactor.toFixed(1) : '—'
      } · exp ${
        snap.expectancy !== null
          ? `${snap.expectancy > 0 ? '+' : ''}${snap.expectancy.toFixed(1)}R`
          : '—'
      }`;

  return (
    <span
      className="num"
      style={{ display: 'inline-flex', flexWrap: 'wrap', alignItems: 'center', gap: 6, fontSize: 11 }}
    >
      <span className="muted">{predText}</span>
      <span aria-hidden="true" className="faint">
        ·
      </span>
      <span className="muted">{sigText}</span>
      <span aria-hidden="true" className="faint">
        ·
      </span>
      {stale ? (
        <>
          <span
            className="chip chip--warn"
            style={{ fontSize: 10 }}
            title="One or more accountability sources failed to respond — showing last known values"
          >
            stale
          </span>
          <span aria-hidden="true" className="faint">
            ·
          </span>
        </>
      ) : null}
      {/* Forecast-health dot: live monitoring status */}
      <span
        className="muted"
        style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
        title={`Forecast health: ${snap.forecastHealth ?? 'unknown'}`}
      >
        <span
          aria-hidden="true"
          style={{
            width: 7,
            height: 7,
            borderRadius: '50%',
            background:
              snap.forecastHealth === 'healthy'
                ? 'var(--ds-bull)'
                : snap.forecastHealth === 'degraded'
                  ? 'var(--ds-warn)'
                  : snap.forecastHealth === 'failing'
                    ? 'var(--ds-bear)'
                    : 'var(--ds-ink-3)',
            display: 'inline-block',
          }}
        />
        forecast {snap.forecastHealth ?? '—'}
      </span>
      <span aria-hidden="true" className="faint">
        ·
      </span>
      {snap.auditCount !== null ? (
        <Link
          href="/signals"
          style={{ color: 'var(--ds-ink-2)', textDecoration: 'underline', textUnderlineOffset: 2 }}
          title="Recent institutional audit entries"
        >
          audit {snap.auditCount.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
        </Link>
      ) : (
        <span className="muted">audit —</span>
      )}
    </span>
  );
});

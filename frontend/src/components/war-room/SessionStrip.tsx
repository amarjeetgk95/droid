'use client';

/* SessionStrip — Phase W7 "should I trade today" strip.
 *
 * One quiet TelemetryStrip row, self-fetching on a 60s poll (hidden-tab
 * aware). Every piece degrades to "—" or a short note independently and never
 * breaks the row. No cards, no heroes — a strip only.
 *
 * Sources (each verified in src/lib/api before use):
 * - breadth ..... api.getMarketBreadth (api/markets.ts) → adv/dec + sentiment.
 * - FII/DII ..... api.getFIIDIIOverview + api.getFlowSnapshot (api/paper.ts) →
 *                 LSR, futures nets, sentiment. Backend fii_dii.py returns
 *                 live:false ALWAYS (daily file, available T+1 18:00 IST), so
 *                 flow is labelled "daily T+1" unconditionally.
 * - events ...... api.getTodayEvents + api.getUpcomingEvents +
 *                 api.getEventRiskOverlay (api/events.ts) → today count plus
 *                 overlay level. Warn tone only when the overlay is elevated
 *                 (blackout window or entry blocked).
 * - futures ..... SKIPPED-WITH-NOTE: no typed futures buildup/rollover client
 *                 exists in src/lib/api (backend /api/v1/futures/* is honestly
 *                 UNAVAILABLE anyway). Stated plainly as "unavailable" via the
 *                 flow snapshot's futures.status — never hidden.
 * - session ..... api.getSessionInfo (api/markets.ts) for holiday/weekend
 *                 honesty.
 *
 * Visuals: TelemetryStrip/TelemetryItem only, .num + en-IN numbers, no
 * globals.css edits, no emoji, no all-caps sentences, no bold figures.
 */

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { TelemetryStrip, TelemetryItem } from '@/components/ui/desk';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';

const POLL_MS = 60_000;

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** Unwrap the { data } envelope; pass through bare payloads. */
function unwrap<T>(res: unknown): T | null {
  if (Array.isArray(res)) return null;
  if (!isRecord(res)) return null;
  const inner = 'data' in res ? res.data : res;
  if (inner === null || inner === undefined) return null;
  return inner as T;
}

function asArray(res: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(res)) return res.filter(isRecord);
  const inner = unwrap<unknown>(res);
  return Array.isArray(inner) ? inner.filter(isRecord) : [];
}

function num(v: unknown): number | null {
  const n = typeof v === 'string' ? Number(v) : v;
  return typeof n === 'number' && Number.isFinite(n) ? n : null;
}

function fmtInt(v: number | null): string {
  if (v === null) return '—';
  return v.toLocaleString('en-IN', { maximumFractionDigits: 0 });
}

/** Humanise SCREAMING enums for display: STRONG_BULLISH → strong bullish. */
function words(v: unknown): string | null {
  if (typeof v !== 'string' || v.trim() === '') return null;
  return v.replace(/_/g, ' ').toLowerCase();
}

function signedInt(v: number | null): string {
  if (v === null) return '—';
  const sign = v > 0 ? '+' : v < 0 ? '−' : '';
  return `${sign}${Math.abs(v).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
}

interface SessionSnap {
  adv: number | null;
  dec: number | null;
  adRatio: number | null;
  breadthSentiment: string | null;
  lsr: number | null;
  fiiFut: number | null;
  diiFut: number | null;
  fiiSentiment: string | null;
  flowScore: number | null;
  flowSentiment: string | null;
  flowDegraded: boolean;
  futuresStatus: string | null;
  todayCount: number | null;
  upcomingCount: number | null;
  overlay: string | null;
  canEnter: boolean | null;
  sizing: number | null;
  tradingDay: boolean | null;
  holidayName: string | null;
  weekend: boolean | null;
  openHr: string | null;
  closeHr: string | null;
}

const EMPTY_SNAP: SessionSnap = {
  adv: null,
  dec: null,
  adRatio: null,
  breadthSentiment: null,
  lsr: null,
  fiiFut: null,
  diiFut: null,
  fiiSentiment: null,
  flowScore: null,
  flowSentiment: null,
  flowDegraded: false,
  futuresStatus: null,
  todayCount: null,
  upcomingCount: null,
  overlay: null,
  canEnter: null,
  sizing: null,
  tradingDay: null,
  holidayName: null,
  weekend: null,
  openHr: null,
  closeHr: null,
};

function strOrNull(v: unknown): string | null {
  return typeof v === 'string' && v.trim() !== '' ? v : null;
}

export const SessionStrip = memo(function SessionStrip({ bare = false }: { bare?: boolean }) {
  const market = useOptionalMarketDataContext();
  const [snap, setSnap] = useState<SessionSnap>(EMPTY_SNAP);
  const [stale, setStale] = useState(false);
  const inFlight = useRef(false);
  const mounted = useRef(true);

  // Sync with ambient MarketDataContext so strip renders immediately without waiting for network
  useEffect(() => {
    if (!market) return;
    setSnap((prev) => {
      const next = { ...prev };
      let changed = false;
      if (market.breadth) {
        if (next.adv !== market.breadth.advancing) { next.adv = market.breadth.advancing; changed = true; }
        if (next.dec !== market.breadth.declining) { next.dec = market.breadth.declining; changed = true; }
        if (next.adRatio !== market.breadth.advance_decline_ratio) { next.adRatio = market.breadth.advance_decline_ratio; changed = true; }
        if (next.breadthSentiment !== words(market.breadth.sentiment)) { next.breadthSentiment = words(market.breadth.sentiment); changed = true; }
      }
      if (market.fiiDii && typeof market.fiiDii === 'object') {
        const o = market.fiiDii as Record<string, unknown>;
        const lsr = num(o.fii_long_short_ratio ?? o.fii_lsr);
        const fiiFut = num(o.fii_futures_net_contracts);
        const diiFut = num(o.dii_futures_net_contracts);
        const fiiSent = words(o.institutional_sentiment ?? o.sentiment);
        if (lsr !== null && next.lsr !== lsr) { next.lsr = lsr; changed = true; }
        if (fiiFut !== null && next.fiiFut !== fiiFut) { next.fiiFut = fiiFut; changed = true; }
        if (diiFut !== null && next.diiFut !== diiFut) { next.diiFut = diiFut; changed = true; }
        if (fiiSent !== null && next.fiiSentiment !== fiiSent) { next.fiiSentiment = fiiSent; changed = true; }
      }
      if (market.marketStatus) {
        if (next.tradingDay !== market.marketStatus.is_trading_day) {
          next.tradingDay = market.marketStatus.is_trading_day;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [market]);

  const load = useCallback(async () => {
    if (typeof document !== 'undefined' && document.hidden) return;
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const [bRes, oRes, fRes, tRes, uRes, rRes, sRes] = await Promise.allSettled([
        api.getMarketBreadth(),
        api.getFIIDIIOverview(),
        api.getFlowSnapshot(),
        api.getTodayEvents(),
        api.getUpcomingEvents(20),
        api.getEventRiskOverlay(),
        api.getSessionInfo(),
      ]);
      if (!mounted.current) return;
      // Per-field failures already degrade to "—"; the strip additionally
      // states that the sweep was partial instead of staying silent.
      setStale([bRes, oRes, fRes, tRes, uRes, rRes, sRes].some((r) => r.status === 'rejected'));
      const next: SessionSnap = { ...EMPTY_SNAP };

      if (bRes.status === 'fulfilled') {
        const b = unwrap<Record<string, unknown>>(bRes.value) ?? {};
        next.adv = num(b.advancing);
        next.dec = num(b.declining);
        next.adRatio = num(b.advance_decline_ratio);
        next.breadthSentiment = words(b.sentiment);
      }
      if (oRes.status === 'fulfilled') {
        const o = unwrap<Record<string, unknown>>(oRes.value) ?? {};
        next.lsr = num(o.fii_long_short_ratio);
        next.fiiFut = num(o.fii_futures_net_contracts);
        next.diiFut = num(o.dii_futures_net_contracts);
        next.fiiSentiment = words(o.institutional_sentiment);
      }
      if (fRes.status === 'fulfilled') {
        const f = unwrap<Record<string, unknown>>(fRes.value) ?? {};
        const flow = isRecord(f.flow) ? f.flow : null;
        const comp = isRecord(f.composite) ? f.composite : null;
        const drift = isRecord(f.drift) ? f.drift : null;
        const fut = isRecord(f.futures) ? f.futures : null;
        // Fallbacks when the overview file is missing but the flow store answers.
        if (next.lsr === null && flow) next.lsr = num(flow.fii_lsr);
        next.flowScore = comp ? num(comp.score) : null;
        next.flowSentiment = comp ? words(comp.sentiment) : null;
        next.flowDegraded = drift ? drift.degraded === true : false;
        next.futuresStatus = fut ? words(fut.status) : null;
      }
      if (tRes.status === 'fulfilled') {
        next.todayCount = asArray(tRes.value).length;
      }
      if (uRes.status === 'fulfilled') {
        next.upcomingCount = asArray(uRes.value).length;
      }
      if (rRes.status === 'fulfilled') {
        const r = unwrap<Record<string, unknown>>(rRes.value) ?? {};
        next.overlay = words(r.proximity_state);
        next.canEnter = typeof r.can_enter === 'boolean' ? r.can_enter : null;
        next.sizing = num(r.sizing_multiplier);
      }
      if (sRes.status === 'fulfilled') {
        const s = unwrap<Record<string, unknown>>(sRes.value) ?? {};
        next.tradingDay = typeof s.is_trading_day === 'boolean' ? s.is_trading_day : null;
        next.weekend = typeof s.is_weekend === 'boolean' ? s.is_weekend : null;
        next.holidayName = strOrNull(s.holiday_name);
        next.openHr = strOrNull(s.market_open);
        next.closeHr = strOrNull(s.market_close);
      }
      setSnap(next);
    } catch {
      // Each piece already degrades independently; a total failure keeps the
      // previous snapshot (marked stale) so the row never flashes empty.
      if (mounted.current) setStale(true);
    } finally {
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    // Stagger initial full fetch by 1.2s to yield bandwidth to primary War Room modules
    const initTimer = setTimeout(() => {
      void load();
    }, 1200);

    const id = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      void load();
    }, POLL_MS);
    return () => {
      mounted.current = false;
      clearTimeout(initTimer);
      clearInterval(id);
    };
  }, [load]);

  // — Breadth: adv/dec + sentiment —
  const breadthKnown = snap.adv !== null || snap.dec !== null;
  const breadthTone =
    snap.adv !== null && snap.dec !== null
      ? snap.adv > snap.dec
        ? 'bull'
        : snap.dec > snap.adv
          ? 'bear'
          : undefined
      : undefined;
  const breadthSub =
    snap.breadthSentiment ?? (snap.adRatio !== null ? `ad ${snap.adRatio.toFixed(2)}` : undefined);

  // — FII/DII: LSR / futures nets / sentiment, flow always daily T+1 —
  const fiiTone = snap.fiiSentiment
    ? snap.fiiSentiment.includes('bull')
      ? 'bull'
      : snap.fiiSentiment.includes('bear')
        ? 'bear'
        : undefined
    : undefined;
  const fiiValue =
    snap.fiiSentiment ?? (snap.lsr !== null ? `lsr ${snap.lsr.toFixed(2)}x` : '—');
  const fiiBits: string[] = [];
  if (snap.lsr !== null && snap.fiiSentiment) fiiBits.push(`lsr ${snap.lsr.toFixed(2)}x`);
  if (snap.fiiFut !== null || snap.diiFut !== null) {
    fiiBits.push(`fut ${signedInt(snap.fiiFut)}/${signedInt(snap.diiFut)}`);
  }
  if (snap.flowSentiment && snap.flowSentiment !== snap.fiiSentiment) {
    fiiBits.push(`flow ${snap.flowSentiment}`);
  }
  if (snap.flowDegraded) fiiBits.push('drift');
  // Backend live flag is always false (daily file) — label is unconditional.
  fiiBits.push('daily T+1');

  // — Events: today count + overlay level, warn tone only when elevated —
  const elevated = snap.overlay === 'blackout window' || snap.canEnter === false;
  const eventsValue = snap.todayCount === null ? '—' : `${fmtInt(snap.todayCount)} today`;
  const eventsBits: string[] = [];
  if (snap.overlay) eventsBits.push(`overlay ${snap.overlay}`);
  if (snap.sizing !== null && elevated) eventsBits.push(`size ×${snap.sizing.toFixed(2)}`);
  if (snap.upcomingCount !== null) eventsBits.push(`${fmtInt(snap.upcomingCount)} upcoming`);

  // — Futures: stated plainly, never hidden (no typed client exists) —
  const futuresValue = snap.futuresStatus ?? 'unavailable';

  // — Session: holiday/weekend honesty —
  const sessionValue =
    snap.tradingDay === null
      ? '—'
      : snap.tradingDay
        ? 'trading day'
        : snap.weekend
          ? 'weekend'
          : 'holiday';
  const sessionSub =
    snap.holidayName ??
    (snap.openHr && snap.closeHr ? `${snap.openHr}–${snap.closeHr}` : undefined);

  return (
    <TelemetryStrip
      style={bare ? { border: 0, borderRadius: 0, background: 'transparent' } : undefined}
    >
      <TelemetryItem
        label="Breadth"
        tone={breadthTone}
        value={<span className="num">{breadthKnown ? `${fmtInt(snap.adv)} adv · ${fmtInt(snap.dec)} dec` : '—'}</span>}
        sub={breadthSub}
        title="Market breadth advances/declines"
      />
      <TelemetryItem
        label="FII/DII"
        tone={fiiTone}
        value={<span className="num">{fiiValue}</span>}
        sub={fiiBits.join(' · ')}
        title="Institutional flow, daily file T+1, never intraday"
      />
      <TelemetryItem
        label="Events"
        tone={elevated ? 'bear' : undefined}
        value={<span className="num">{eventsValue}</span>}
        sub={eventsBits.length > 0 ? eventsBits.join(' · ') : undefined}
        title="Scheduled-event risk overlay"
      />
      <TelemetryItem
        label="Futures"
        value={<span className="num">{futuresValue}</span>}
        sub="no live feed"
        title="No live futures feed; basis and open interest are not synthesised"
      />
      <TelemetryItem
        label="Session"
        value={<span className="num">{sessionValue}</span>}
        sub={sessionSub}
        title="Trading-day calendar"
      />
      {stale ? (
        <TelemetryItem
          label="Feed"
          value={<span className="num">stale</span>}
          sub="source unreachable"
          title="One or more session sources failed; values shown are the last known sweep"
        />
      ) : null}
    </TelemetryStrip>
  );
});

'use client';

/* Intel-desk data hooks: institutional dashboards + event intelligence.
   Pattern mirrors useSignalDesk — Promise.allSettled loads, useSmartInterval
   polling (timers live only here, never in components), errorMessage. */

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import { getObj, dataFreshness, maxPayloadTimestampMs } from '@/lib/signalsNormalize';
import {
  summarizeDataHealth,
  summarizeFeedHealth,
  summarizeMIDashboard,
  toAuditRows,
  toInstSignalRow,
  type AuditRow,
  type FeedRow,
  type HealthRow,
  type InstSignalRow,
  type MiSummary,
} from '@/lib/intelDesk';
import type {
  CanonicalEvent,
  EventAlert,
  EventComparable,
  EventOutcome,
  EventRiskParameters,
  EventScoreSnapshot,
  EventTrackRecord,
  LiveOpportunityResponse,
  PredictionSnapshot,
  ShadowSignalRecord,
  SourceHealthTelemetry,
} from '@/lib/event-types';
import { useSmartInterval } from './useSmartInterval';

export type DeskResult = { ok: boolean; message: string };

/* ---------------- institutional ---------------- */

export type InstSignalDetail = {
  raw: Record<string, unknown>;
  ttlRemainingMs: number | null;
  expired: boolean | null;
  fsmState: string | null;
};

export type InstitutionalDeskState = {
  mi: MiSummary | null;
  miRaw: Record<string, unknown> | null;
  healthRows: HealthRow[];
  healthOverall: Record<string, string>;
  callsPuts: Record<string, unknown> | null;
  miFull: Record<string, unknown> | null;
  signals: InstSignalRow[];
  history: AuditRow[];
  audit: AuditRow[];
  feeds: FeedRow[];
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  updatedAt: number | null;
  /** Age of `updatedAt` in ms. Null when the payload carried no instant. */
  ageMs: number | null;
  /** True when `updatedAt` is missing or older than the staleness window. */
  stale: boolean;
  source: 'rest';
  liveSource: 'rest';
  refresh: () => Promise<void>;
  loadSignalDetail: (signalId: string) => Promise<InstSignalDetail | null>;
  loadFeedDetail: (instrumentId: string) => Promise<Record<string, unknown> | null>;
  checkTtl: (signalId: string) => Promise<DeskResult & { remainingMs?: number | null; expired?: boolean | null }>;
  transition: (signalId: string, toState: string) => Promise<DeskResult>;
  casExecute: (signalId: string) => Promise<DeskResult>;
  tripFeed: (instrumentId: string, anomaly: string, reason: string) => Promise<DeskResult>;
  resyncFeed: (instrumentId: string) => Promise<DeskResult>;
  evaluateMI: (payload: Record<string, unknown>) => Promise<{ ok: boolean; message: string; data: Record<string, unknown> | null }>;
  evaluateBreakout: (payload: Record<string, unknown>) => Promise<{ ok: boolean; message: string; data: Record<string, unknown> | null }>;
  evaluateRisk: (payload: Record<string, unknown>) => Promise<{ ok: boolean; message: string; data: Record<string, unknown> | null }>;
  validateContract: (instrumentId: string, price: string, quantity: string) => Promise<{ ok: boolean; message: string; data: Record<string, unknown> | null }>;
};

export function useInstitutionalDesk(
  instrument: string,
  options: { pollMs?: number | null } = {},
): InstitutionalDeskState {
  const { pollMs = null } = options;
  const [mi, setMi] = useState<MiSummary | null>(null);
  const [miRaw, setMiRaw] = useState<Record<string, unknown> | null>(null);
  const [healthRows, setHealthRows] = useState<HealthRow[]>([]);
  const [healthOverall, setHealthOverall] = useState<Record<string, string>>({});
  const [callsPuts, setCallsPuts] = useState<Record<string, unknown> | null>(null);
  const [miFull, setMiFull] = useState<Record<string, unknown> | null>(null);
  const [signals, setSignals] = useState<InstSignalRow[]>([]);
  const [history, setHistory] = useState<AuditRow[]>([]);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [feeds, setFeeds] = useState<FeedRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const requestIdRef = useRef(0);
  const instrumentRef = useRef(instrument);
  instrumentRef.current = instrument;

  const load = useCallback(async (showSpinner: boolean) => {
    const requestId = ++requestIdRef.current;
    if (showSpinner) setRefreshing(true);
    const inst = instrumentRef.current;
    const [miRes, healthRes, cpRes, fullRes, sigRes, histRes, auditRes, feedRes] =
      await Promise.allSettled([
        api.getInstitutionalDashboardMI(inst),
        api.getInstitutionalDataHealthDashboard(),
        api.getCallsPutsFull(inst),
        api.getMIFull(inst),
        api.getInstitutionalSignalsActive({ instrument: inst }),
        api.getInstitutionalSignalsHistory(20),
        api.getInstitutionalAuditRecent(20),
        api.getInstitutionalFeedHealth(),
      ]);
    if (requestIdRef.current !== requestId) return;

    let firstError: string | null = null;
    if (miRes.status === 'fulfilled') {
      setMiRaw(getObj(miRes.value) ?? null);
      setMi(summarizeMIDashboard(miRes.value));
    } else firstError = errorMessage(miRes.reason, 'Market intelligence unavailable');
    if (healthRes.status === 'fulfilled') {
      const { rows, overall } = summarizeDataHealth(healthRes.value);
      setHealthRows(rows);
      setHealthOverall(overall);
    } else {
      firstError = firstError ?? errorMessage(healthRes.reason, 'Data health unavailable');
    }
    if (cpRes.status === 'fulfilled') setCallsPuts(getObj(cpRes.value) ?? null);
    else firstError = firstError ?? errorMessage(cpRes.reason, 'Calls/puts unavailable');
    if (fullRes.status === 'fulfilled') setMiFull(getObj(fullRes.value) ?? null);
    else firstError = firstError ?? errorMessage(fullRes.reason, 'Full MI unavailable');
    if (sigRes.status === 'fulfilled') {
      setSignals(
        (sigRes.value.signals ?? [])
          .map(toInstSignalRow)
          .filter((row): row is InstSignalRow => row !== null),
      );
    } else {
      firstError = firstError ?? errorMessage(sigRes.reason, 'Institutional signals unavailable');
    }
    if (histRes.status === 'fulfilled') setHistory(toAuditRows(histRes.value.records));
    if (auditRes.status === 'fulfilled') setAudit(toAuditRows(auditRes.value.records));
    if (feedRes.status === 'fulfilled') setFeeds(summarizeFeedHealth(feedRes.value));
    else firstError = firstError ?? errorMessage(feedRes.reason, 'Feed health unavailable');

    setError(firstError);
    // Payload instants only — a failed or undated batch keeps the last age.
    // Never bump to Date.now() to mask an outage.
    const payloadTs = maxPayloadTimestampMs([
      miRes.status === 'fulfilled' ? miRes.value : null,
      healthRes.status === 'fulfilled' ? healthRes.value : null,
      cpRes.status === 'fulfilled' ? cpRes.value : null,
      fullRes.status === 'fulfilled' ? fullRes.value : null,
      sigRes.status === 'fulfilled' ? sigRes.value : null,
      histRes.status === 'fulfilled' ? histRes.value : null,
      auditRes.status === 'fulfilled' ? auditRes.value : null,
      feedRes.status === 'fulfilled' ? feedRes.value : null,
    ]);
    if (payloadTs !== null) {
      setUpdatedAt(payloadTs);
    }
    setLoading(false);
    if (showSpinner) setRefreshing(false);
  }, []);

  useEffect(() => {
    setLoading(true);
    void load(false);
  }, [load, instrument]);

  useSmartInterval(useCallback(() => load(false), [load]), pollMs, { fireOnMount: false });

  const refresh = useCallback(async () => {
    await load(true);
  }, [load]);

  const loadSignalDetail = useCallback(async (signalId: string): Promise<InstSignalDetail | null> => {
    try {
      const [detailRes, ttlRes] = await Promise.allSettled([
        api.getInstitutionalSignal(signalId),
        api.getInstitutionalSignalTtl(signalId),
      ]);
      if (detailRes.status !== 'fulfilled') return null;
      const raw = getObj(detailRes.value) ?? {};
      const ttl = ttlRes.status === 'fulfilled' ? ttlRes.value : null;
      return {
        raw,
        ttlRemainingMs: ttl?.ttl_remaining_ms ?? null,
        expired: ttl?.is_expired ?? (typeof raw.is_expired === 'boolean' ? raw.is_expired : null),
        fsmState:
          ttl?.fsm_state ??
          (typeof raw.fsm_state === 'string' ? raw.fsm_state : null),
      };
    } catch {
      return null;
    }
  }, []);

  const checkTtl = useCallback(async (signalId: string) => {
    try {
      const ttl = await api.getInstitutionalSignalTtl(signalId);
      await load(false);
      const remaining = ttl.ttl_remaining_ms;
      return {
        ok: true,
        remainingMs: remaining,
        expired: ttl.is_expired,
        message:
          ttl.is_expired || ttl.valid === false
            ? `Signal ${signalId} TTL expired${ttl.error ? ` — ${ttl.error}` : ''}.`
            : `Signal ${signalId} TTL valid (${remaining ?? '—'} ms remaining).`,
      };
    } catch (err) {
      return { ok: false, message: errorMessage(err, 'TTL check failed') };
    }
  }, [load]);

  const loadFeedDetail = useCallback(async (instrumentId: string) => {
    try {
      return (await api.getInstitutionalFeedHealthOne(instrumentId)) as Record<string, unknown>;
    } catch {
      return null;
    }
  }, []);

  const transition = useCallback(async (signalId: string, toState: string): Promise<DeskResult> => {
    try {
      await api.transitionInstitutionalSignal(signalId, toState);
      await load(false);
      return { ok: true, message: `Signal transitioned to ${toState}.` };
    } catch (err) {
      return { ok: false, message: errorMessage(err, 'Transition failed') };
    }
  }, [load]);

  const casExecute = useCallback(async (signalId: string): Promise<DeskResult> => {
    try {
      await api.casInstitutionalSignalExecution(signalId);
      await load(false);
      return { ok: true, message: 'Signal moved to EXECUTION_PENDING via CAS.' };
    } catch (err) {
      return { ok: false, message: errorMessage(err, 'CAS execution failed') };
    }
  }, [load]);

  const tripFeed = useCallback(async (instrumentId: string, anomaly: string, reason: string): Promise<DeskResult> => {
    try {
      await api.tripFeedCircuit(instrumentId, anomaly, reason);
      await load(false);
      return { ok: true, message: `Feed circuit tripped for ${instrumentId}.` };
    } catch (err) {
      return { ok: false, message: errorMessage(err, 'Feed trip failed') };
    }
  }, [load]);

  const resyncFeed = useCallback(async (instrumentId: string): Promise<DeskResult> => {
    try {
      await api.resyncFeedCircuit(instrumentId);
      await load(false);
      return { ok: true, message: `Resync requested for ${instrumentId}.` };
    } catch (err) {
      return { ok: false, message: errorMessage(err, 'Resync request failed') };
    }
  }, [load]);

  const runEval = useCallback(
    async (fn: () => Promise<unknown>, label: string) => {
      try {
        const data = await fn();
        return { ok: true, message: `${label} evaluated.`, data: getObj(data) ?? null };
      } catch (err) {
        return { ok: false, message: errorMessage(err, `${label} evaluation failed`), data: null };
      }
    },
    [],
  );

  const evaluateMI = useCallback(
    (payload: Record<string, unknown>) =>
      runEval(() => api.evaluateMarketIntelligence(payload), 'Market intelligence'),
    [runEval],
  );

  const evaluateBreakout = useCallback(
    (payload: Record<string, unknown>) =>
      runEval(() => api.evaluateBreakout(payload), 'Breakout'),
    [runEval],
  );

  const evaluateRisk = useCallback(
    (payload: Record<string, unknown>) =>
      runEval(() => api.evaluatePortfolioRisk(payload), 'Portfolio risk'),
    [runEval],
  );

  const validateContract = useCallback(
    async (instrumentId: string, price: string, quantity: string) => {
      try {
        const data = await api.validateContract(instrumentId, price, quantity);
        return { ok: true, message: 'Contract validated.', data: getObj(data) ?? null };
      } catch (err) {
        return { ok: false, message: errorMessage(err, 'Contract validation failed'), data: null };
      }
    },
    [],
  );

  const freshness = dataFreshness(updatedAt);

  return {
    mi,
    miRaw,
    healthRows,
    healthOverall,
    callsPuts,
    miFull,
    signals,
    history,
    audit,
    feeds,
    loading,
    refreshing,
    error,
    updatedAt,
    ageMs: freshness.ageMs,
    stale: freshness.stale,
    source: 'rest' as const,
    liveSource: 'rest' as const,
    refresh,
    loadSignalDetail,
    loadFeedDetail,
    checkTtl,
    transition,
    casExecute,
    tripFeed,
    resyncFeed,
    evaluateMI,
    evaluateBreakout,
    evaluateRisk,
    validateContract,
  };
}

/* ---------------- events ---------------- */

export type EventDetailBundle = {
  detail: CanonicalEvent | null;
  scores: EventScoreSnapshot | null;
  comparables: EventComparable[] | null;
  prediction: PredictionSnapshot | null;
  liveOpp: LiveOpportunityResponse | null;
  outcome: EventOutcome | null;
  errors: string[];
};

export type EventsDeskState = {
  today: CanonicalEvent[];
  upcoming: CanonicalEvent[];
  trackRecord: EventTrackRecord | null;
  sources: SourceHealthTelemetry | null;
  shadow: ShadowSignalRecord[];
  overlay: EventRiskParameters | null;
  alerts: EventAlert[] | null;
  alertsLoading: boolean;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  updatedAt: number | null;
  /** Age of `updatedAt` in ms. Null when the payload carried no instant. */
  ageMs: number | null;
  /** True when `updatedAt` is missing or older than the staleness window. */
  stale: boolean;
  source: 'rest';
  liveSource: 'rest';
  detail: EventDetailBundle | null;
  detailLoading: boolean;
  selectedId: string | null;
  refresh: () => Promise<void>;
  loadAlerts: () => Promise<void>;
  ackAlert: (alertId: string) => Promise<DeskResult>;
  syncRbi: () => Promise<DeskResult & { count?: number }>;
  syncCorporate: () => Promise<DeskResult & { count?: number }>;
  createManual: (payload: Record<string, unknown>) => Promise<DeskResult>;
  openEvent: (eventId: string) => Promise<void>;
  closeEvent: () => void;
};

function asEventList(value: unknown): CanonicalEvent[] {
  return Array.isArray(value) ? value.filter((e): e is CanonicalEvent => getObj(e) !== null) : [];
}

export function useEventsDesk(
  underlying: string,
  options: { pollMs?: number | null } = {},
): EventsDeskState {
  const { pollMs = null } = options;
  const [today, setToday] = useState<CanonicalEvent[]>([]);
  const [upcoming, setUpcoming] = useState<CanonicalEvent[]>([]);
  const [trackRecord, setTrackRecord] = useState<EventTrackRecord | null>(null);
  const [sources, setSources] = useState<SourceHealthTelemetry | null>(null);
  const [shadow, setShadow] = useState<ShadowSignalRecord[]>([]);
  const [overlay, setOverlay] = useState<EventRiskParameters | null>(null);
  const [alerts, setAlerts] = useState<EventAlert[] | null>(null);
  const [alertsLoading, setAlertsLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [detail, setDetail] = useState<EventDetailBundle | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const requestIdRef = useRef(0);
  const detailRequestRef = useRef(0);
  const underlyingRef = useRef(underlying);
  underlyingRef.current = underlying;

  const load = useCallback(async (showSpinner: boolean) => {
    const requestId = ++requestIdRef.current;
    if (showSpinner) setRefreshing(true);
    const under = underlyingRef.current;
    const [todayRes, upRes, trackRes, srcRes, shadowRes, overlayRes] = await Promise.allSettled([
      api.getTodayEvents(),
      api.getUpcomingEvents(50),
      api.getEventTrackRecord(),
      api.getEventSourcesHealth(),
      api.getEventShadowSignals(),
      api.getEventRiskOverlay(under),
    ]);
    if (requestIdRef.current !== requestId) return;

    let firstError: string | null = null;
    if (todayRes.status === 'fulfilled') setToday(asEventList(todayRes.value));
    else firstError = errorMessage(todayRes.reason, "Today's events unavailable");
    if (upRes.status === 'fulfilled') setUpcoming(asEventList(upRes.value));
    else firstError = firstError ?? errorMessage(upRes.reason, 'Upcoming events unavailable');
    if (trackRes.status === 'fulfilled') setTrackRecord(getObj(trackRes.value) as EventTrackRecord | null);
    else firstError = firstError ?? errorMessage(trackRes.reason, 'Track record unavailable');
    if (srcRes.status === 'fulfilled') setSources(getObj(srcRes.value) as SourceHealthTelemetry | null);
    else firstError = firstError ?? errorMessage(srcRes.reason, 'Source health unavailable');
    if (shadowRes.status === 'fulfilled') {
      setShadow(Array.isArray(shadowRes.value) ? shadowRes.value : []);
    } else {
      firstError = firstError ?? errorMessage(shadowRes.reason, 'Shadow signals unavailable');
    }
    if (overlayRes.status === 'fulfilled') {
      setOverlay(getObj(overlayRes.value) as EventRiskParameters | null);
    } else {
      firstError = firstError ?? errorMessage(overlayRes.reason, 'Risk overlay unavailable');
    }

    setError(firstError);
    // Payload instants only — a failed or undated batch keeps the last age.
    const payloadTs = maxPayloadTimestampMs([
      todayRes.status === 'fulfilled' ? todayRes.value : null,
      upRes.status === 'fulfilled' ? upRes.value : null,
      trackRes.status === 'fulfilled' ? trackRes.value : null,
      srcRes.status === 'fulfilled' ? srcRes.value : null,
      shadowRes.status === 'fulfilled' ? shadowRes.value : null,
      overlayRes.status === 'fulfilled' ? overlayRes.value : null,
    ]);
    if (payloadTs !== null) {
      setUpdatedAt(payloadTs);
    }
    setLoading(false);
    if (showSpinner) setRefreshing(false);
  }, []);

  useEffect(() => {
    setLoading(true);
    void load(false);
  }, [load, underlying]);

  useSmartInterval(useCallback(() => load(false), [load]), pollMs, { fireOnMount: false });

  const refresh = useCallback(async () => {
    await load(true);
  }, [load]);

  const loadAlerts = useCallback(async () => {
    setAlertsLoading(true);
    try {
      const value = await api.getEventAlertsQueue();
      setAlerts(Array.isArray(value) ? value : []);
    } catch {
      setAlerts([]);
    } finally {
      setAlertsLoading(false);
    }
  }, []);

  const ackAlert = useCallback(async (alertId: string): Promise<DeskResult> => {
    try {
      await api.ackEventAlert(alertId);
      const value = await api.getEventAlertsQueue().catch(() => null);
      if (Array.isArray(value)) setAlerts(value);
      return { ok: true, message: `Alert ${alertId} acknowledged.` };
    } catch (err) {
      return { ok: false, message: errorMessage(err, 'Alert ack failed') };
    }
  }, []);

  const syncRbi = useCallback(async () => {
    try {
      const events = await api.syncRbiEvents();
      await load(false);
      const count = Array.isArray(events) ? events.length : 0;
      return { ok: true, message: `RBI sync complete — ${count} event(s).`, count };
    } catch (err) {
      return { ok: false, message: errorMessage(err, 'RBI sync failed') };
    }
  }, [load]);

  const syncCorporate = useCallback(async () => {
    try {
      const events = await api.syncCorporateEvents();
      await load(false);
      const count = Array.isArray(events) ? events.length : 0;
      return { ok: true, message: `Corporate sync complete — ${count} event(s).`, count };
    } catch (err) {
      return { ok: false, message: errorMessage(err, 'Corporate sync failed') };
    }
  }, [load]);

  const createManual = useCallback(async (payload: Record<string, unknown>): Promise<DeskResult> => {
    try {
      await api.createManualEvent(payload);
      await load(false);
      return { ok: true, message: 'Manual event recorded.' };
    } catch (err) {
      return { ok: false, message: errorMessage(err, 'Manual entry failed') };
    }
  }, [load]);

  const openEvent = useCallback(async (eventId: string) => {
    const requestId = ++detailRequestRef.current;
    setSelectedId(eventId);
    setDetailLoading(true);
    setDetail(null);
    const [detailRes, scoresRes, compRes, predRes, liveRes, outcomeRes] = await Promise.allSettled([
      api.getEventDetail(eventId),
      api.getEventScores(eventId),
      api.getEventComparables(eventId),
      api.getEventPrediction(eventId),
      api.getEventLiveOpportunity(eventId),
      api.getEventOutcome(eventId),
    ]);
    if (detailRequestRef.current !== requestId) return;
    const errors: string[] = [];
    const take = <T,>(res: PromiseSettledResult<T>, label: string): T | null => {
      if (res.status === 'fulfilled') return res.value;
      errors.push(`${label}: ${errorMessage(res.reason, 'unavailable')}`);
      return null;
    };
    setDetail({
      detail: take(detailRes, 'detail'),
      scores: take(scoresRes, 'scores'),
      comparables: take(compRes, 'comparables'),
      prediction: take(predRes, 'prediction'),
      liveOpp: take(liveRes, 'live opportunity'),
      outcome: take(outcomeRes, 'outcome'),
      errors,
    });
    setDetailLoading(false);
  }, []);

  const closeEvent = useCallback(() => {
    detailRequestRef.current += 1;
    setSelectedId(null);
    setDetail(null);
    setDetailLoading(false);
  }, []);

  const freshness = dataFreshness(updatedAt);

  return {
    today,
    upcoming,
    trackRecord,
    sources,
    shadow,
    overlay,
    alerts,
    alertsLoading,
    loading,
    refreshing,
    error,
    updatedAt,
    ageMs: freshness.ageMs,
    stale: freshness.stale,
    source: 'rest' as const,
    liveSource: 'rest' as const,
    detail,
    detailLoading,
    selectedId,
    refresh,
    loadAlerts,
    ackAlert,
    syncRbi,
    syncCorporate,
    createManual,
    openEvent,
    closeEvent,
  };
}

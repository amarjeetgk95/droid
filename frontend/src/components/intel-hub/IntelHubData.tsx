'use client';

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { api } from '@/lib/api';
import { toNumber } from '@/lib/coerce';
import { errorMessage as canonicalErrorMessage } from '@/lib/errors';
import { useInstrument, type SupportedInstrument } from '@/context/InstrumentContext';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';
import { usePolling } from '@/hooks/usePolling';
import { regimeFromSummary } from '@/lib/regime';
import { isUsableRegimeOverview } from '@/components/markets/truthful';
import type { MarketRegimeOverview } from '@/lib/types';

/** Shared poll cadences for the intel hub. */
export const MI_POLL_MS = 5_000;
export const REGIME_POLL_MS = 15_000;

/* ─────────────────────────── coercion helpers ─────────────────────────── */

export function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

export function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null;
}

export function asNumber(value: unknown): number | null {
  return toNumber(value);
}

export function asBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

export function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (entry): entry is string => typeof entry === 'string' && entry.trim() !== '',
  );
}

/** Intel-hub wrapper over the canonical helper; fallback text unchanged. */
export function errorMessage(err: unknown): string {
  return canonicalErrorMessage(err, 'Request failed');
}

/* ────────────────────────── parsed MI-full shapes ─────────────────────── */

export interface MiEvidenceItem {
  dimension: string;
  signal: string;
  detail: string;
  state: string;
}

export interface MiShortHorizon {
  present: boolean;
  strategy: string | null;
  direction: string | null;
  status: string | null;
  confidence: number | null;
  horizonMinutes: number | null;
  entryZone: string[];
  stopLoss: string | null;
  targetZone: string[];
  falseBreakoutRisk: number | null;
  reason: string | null;
}

export interface MiContinuation {
  present: boolean;
  strategy: string | null;
  direction: string | null;
  status: string | null;
  confidence: number | null;
  maxHoldingMinutes: number | null;
  reason: string | null;
  invalidation: string | null;
}

export interface MiBreakout {
  present: boolean;
  direction: string | null;
  status: string | null;
  confidence: number | null;
  breakoutLevel: string | null;
  breakoutPressure: number | null;
  breakdownPressure: number | null;
  falseBreakoutRisk: number | null;
  breakoutQuality: number | null;
  reason: string | null;
  supporting: string[];
  conflicts: string[];
}

export interface MiEvidenceSet {
  supporting: MiEvidenceItem[];
  conflicting: MiEvidenceItem[];
  missing: string[];
  stale: string[];
  invalid: string[];
}

export interface MiFeedHealth {
  health: string | null;
  reason: string | null;
  circuitState: string | null;
  stalenessMs: number | null;
  isStale: boolean | null;
  usedCache: boolean | null;
}

export interface MiSession {
  isOpen: boolean | null;
  sessionType: string | null;
  isTradable: boolean | null;
  nowIst: string | null;
}

export interface MiDataHealth {
  feed: string | null;
  dataHealth: string | null;
  clockSync: string | null;
  sequence: string | null;
  contract: string | null;
  snapshot: string | null;
}

export interface MiFull {
  instrumentId: string | null;
  displayName: string | null;
  price: number | null;
  regime: string | null;
  momentum: string | null;
  volatility: string | null;
  multiTimeframe: Record<string, string> | null;
  scores: {
    breakoutPressure: number | null;
    breakdownPressure: number | null;
    falseBreakoutRisk: number | null;
  };
  breakout: MiBreakout;
  shortHorizon: MiShortHorizon;
  continuation: MiContinuation;
  evidence: MiEvidenceSet;
  feed: MiFeedHealth;
  session: MiSession;
  dataHealth: MiDataHealth;
  sequenceGap: boolean | null;
  generatedAtMs: number | null;
}

function parseStringMap(value: unknown): Record<string, string> | null {
  const rec = asRecord(value);
  if (!rec) return null;
  const out: Record<string, string> = {};
  for (const [key, raw] of Object.entries(rec)) {
    const text = typeof raw === 'string' ? raw : typeof raw === 'number' ? String(raw) : null;
    if (text !== null && text.trim() !== '') out[key] = text;
  }
  return Object.keys(out).length > 0 ? out : null;
}

function parseEvidenceItems(value: unknown): MiEvidenceItem[] {
  if (!Array.isArray(value)) return [];
  const out: MiEvidenceItem[] = [];
  for (const entry of value) {
    const rec = asRecord(entry);
    if (!rec) continue;
    const dimension = asString(rec.dimension) ?? '';
    const signal = asString(rec.signal) ?? '';
    if (dimension === '' && signal === '') continue;
    out.push({
      dimension,
      signal,
      detail: asString(rec.detail) ?? '',
      state: asString(rec.state) ?? 'UNKNOWN',
    });
  }
  return out;
}

function parseShortHorizon(value: unknown): MiShortHorizon {
  const rec = asRecord(value);
  const stopLoss = asString(rec?.stop_loss);
  return {
    present: rec !== null,
    strategy: asString(rec?.strategy),
    direction: asString(rec?.direction),
    status: asString(rec?.status),
    confidence: asNumber(rec?.confidence),
    horizonMinutes: asNumber(rec?.horizon_minutes),
    entryZone: asStringArray(rec?.entry_zone),
    stopLoss: stopLoss === '0' ? null : stopLoss,
    targetZone: asStringArray(rec?.target_zone),
    falseBreakoutRisk: asNumber(rec?.false_breakout_risk),
    reason: asString(rec?.reason),
  };
}

function parseContinuation(value: unknown): MiContinuation {
  const rec = asRecord(value);
  return {
    present: rec !== null,
    strategy: asString(rec?.strategy),
    direction: asString(rec?.direction),
    status: asString(rec?.status),
    confidence: asNumber(rec?.confidence),
    maxHoldingMinutes: asNumber(rec?.max_holding_minutes),
    reason: asString(rec?.reason),
    invalidation: asString(rec?.invalidation),
  };
}

function parseBreakout(value: unknown): MiBreakout {
  const rec = asRecord(value);
  return {
    present: rec !== null,
    direction: asString(rec?.direction),
    status: asString(rec?.status),
    confidence: asNumber(rec?.confidence),
    breakoutLevel: asString(rec?.breakout_level),
    breakoutPressure: asNumber(rec?.breakout_pressure),
    breakdownPressure: asNumber(rec?.breakdown_pressure),
    falseBreakoutRisk: asNumber(rec?.false_breakout_risk),
    breakoutQuality: asNumber(rec?.breakout_quality),
    reason: asString(rec?.reason),
    supporting: asStringArray(rec?.supporting),
    conflicts: asStringArray(rec?.conflicts),
  };
}

/**
 * Parse the RAW `/market-intelligence/{instrument}/full` payload. Every field
 * is optional-by-evidence: missing values stay `null` so panels can render an
 * explicit unavailable state instead of a fabricated placeholder.
 */
export function parseMiFull(raw: Record<string, unknown>): MiFull {
  const header = asRecord(raw.header);
  const marketState = asRecord(raw.market_state);
  const miBlock = asRecord(raw.market_intelligence);
  const priceAction = asRecord(raw.price_action);
  const details = asRecord(raw.details);
  const evidenceRaw = asRecord(raw.evidence);
  const feedRaw = asRecord(raw.feed_health);
  const sessionRaw = asRecord(raw.session);
  const dataHealthRaw = asRecord(raw.data_health);
  const sequenceRaw = asRecord(raw.sequence);
  const scoresRaw = asRecord(marketState?.scores) ?? miBlock;

  const multiTimeframe = parseStringMap(
    details?.multi_timeframe ?? miBlock?.multi_timeframe ?? marketState?.multi_timeframe,
  );

  const evidenceSource = parseEvidenceItems(raw.supporting_evidence);
  const evidenceAgainst = parseEvidenceItems(raw.conflicting_evidence);

  const breakout = parseBreakout(raw.breakout);

  return {
    instrumentId: asString(raw.instrument_id) ?? asString(miBlock?.instrument),
    displayName: asString(header?.display_name),
    price: asNumber(header?.price) ?? asNumber(miBlock?.spot_price),
    regime: asString(marketState?.regime) ?? asString(miBlock?.regime),
    momentum:
      asString(marketState?.momentum) ??
      asString(priceAction?.momentum) ??
      asString(miBlock?.price_action ? asRecord(miBlock.price_action)?.momentum : null),
    volatility: asString(marketState?.volatility),
    multiTimeframe,
    scores: {
      breakoutPressure:
        asNumber(scoresRaw?.breakout_pressure) ?? breakout.breakoutPressure,
      breakdownPressure:
        asNumber(scoresRaw?.breakdown_pressure) ?? breakout.breakdownPressure,
      falseBreakoutRisk:
        asNumber(scoresRaw?.false_breakout_risk) ?? breakout.falseBreakoutRisk,
    },
    breakout: {
      ...breakout,
      breakoutPressure: breakout.breakoutPressure ?? asNumber(scoresRaw?.breakout_pressure),
      breakdownPressure: breakout.breakdownPressure ?? asNumber(scoresRaw?.breakdown_pressure),
      falseBreakoutRisk: breakout.falseBreakoutRisk ?? asNumber(scoresRaw?.false_breakout_risk),
      breakoutLevel:
        breakout.breakoutLevel ?? asString(asRecord(raw.levels)?.breakout_trigger),
    },
    shortHorizon: parseShortHorizon(raw.short_horizon),
    continuation: parseContinuation(raw.continuation),
    evidence: {
      supporting: evidenceSource.length > 0 ? evidenceSource : parseEvidenceItems(evidenceRaw?.supporting),
      conflicting: evidenceAgainst.length > 0 ? evidenceAgainst : parseEvidenceItems(evidenceRaw?.conflicting),
      missing: asStringArray(evidenceRaw?.missing),
      stale: asStringArray(evidenceRaw?.stale),
      invalid: asStringArray(evidenceRaw?.invalid),
    },
    feed: {
      health: asString(feedRaw?.health) ?? asString(header?.live_status) ?? asString(dataHealthRaw?.feed),
      reason: asString(feedRaw?.reason),
      circuitState: asString(feedRaw?.circuit_state),
      stalenessMs:
        asNumber(feedRaw?.staleness_ms) ?? asNumber(dataHealthRaw?.last_event_age_ms),
      isStale: asBoolean(feedRaw?.is_stale),
      usedCache: asBoolean(feedRaw?.used_cache) ?? asBoolean(header?.used_cache),
    },
    session: {
      isOpen: asBoolean(sessionRaw?.is_open),
      sessionType:
        asString(sessionRaw?.session_type) ??
        asString(sessionRaw?.session_label) ??
        asString(header?.session),
      isTradable: asBoolean(sessionRaw?.is_tradable),
      nowIst: asString(sessionRaw?.now_ist),
    },
    dataHealth: {
      feed: asString(dataHealthRaw?.feed),
      dataHealth: asString(dataHealthRaw?.data_health),
      clockSync: asString(dataHealthRaw?.clock_sync),
      sequence: asString(dataHealthRaw?.sequence),
      contract: asString(dataHealthRaw?.contract),
      snapshot: asString(dataHealthRaw?.snapshot),
    },
    sequenceGap: asBoolean(sequenceRaw?.gap_detected),
    generatedAtMs: asNumber(raw.generated_at_ms),
  };
}

/* ────────────────────────────── provider ──────────────────────────────── */

interface TaggedState<T> {
  instrument: SupportedInstrument;
  data: T | null;
  error: string | null;
  at: number | null;
}

export interface IntelHubValue {
  instrument: SupportedInstrument;
  mi: MiFull | null;
  miError: string | null;
  miStatus: 'loading' | 'ready' | 'error';
  miUpdatedAt: number | null;
  regime: MarketRegimeOverview | null;
  regimeError: string | null;
  regimeLoading: boolean;
}

const IntelHubContext = createContext<IntelHubValue | null>(null);

/**
 * Single shared source for the intel hub: one `market-intelligence/{id}/full`
 * poll and one `regime/{id}/overview` poll per cycle, consumed by every panel.
 * Instrument switches invalidate in-flight responses via an incrementing
 * sequence AND an AbortSignal, so a late response for the previous symbol can
 * never overwrite the new one.
 */
export const IntelHubProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { instrument } = useInstrument();
  // Summary's regime leg covers NIFTY; reuse it rather than fetch the same
  // diagnosis a second time on this route.
  const market = useOptionalMarketDataContext();
  const contextRegime = regimeFromSummary(market?.regimeOverview, instrument);
  const [miState, setMiState] = useState<TaggedState<MiFull> | null>(null);
  const [regimeState, setRegimeState] = useState<TaggedState<MarketRegimeOverview> | null>(null);
  const [regimeLoading, setRegimeLoading] = useState(true);

  const miSeqRef = useRef(0);
  const regimeSeqRef = useRef(0);
  const miAbortRef = useRef<AbortController | null>(null);

  const fetchMi = useCallback(async () => {
    const seq = ++miSeqRef.current;
    miAbortRef.current?.abort();
    const controller = new AbortController();
    miAbortRef.current = controller;
    try {
      const raw = await api.getMIFull(instrument, { signal: controller.signal });
      if (seq !== miSeqRef.current || controller.signal.aborted) return;
      setMiState({ instrument, data: parseMiFull(raw), error: null, at: Date.now() });
    } catch (err) {
      if (seq !== miSeqRef.current || controller.signal.aborted) return;
      const message = errorMessage(err);
      setMiState((prev) =>
        prev && prev.instrument === instrument
          ? { ...prev, error: message }
          : { instrument, data: null, error: message, at: null },
      );
    }
  }, [instrument]);

  const fetchRegime = useCallback(async () => {
    const seq = ++regimeSeqRef.current;
    setRegimeLoading(true);
    try {
      const shared = contextRegime;
      const res = shared
        ? { data: shared, error: null as string | null }
        : await api.getRegimeOverview(instrument);
      if (seq !== regimeSeqRef.current) return;
      const overview = res?.data ?? null;
      const usable = isUsableRegimeOverview(overview, instrument) ? overview : null;
      setRegimeState({
        instrument,
        data: usable,
        error: usable
          ? res?.error ?? null
          : res?.error ?? `No usable regime diagnosis returned for ${instrument}`,
        at: Date.now(),
      });
    } catch (err) {
      if (seq !== regimeSeqRef.current) return;
      setRegimeState({ instrument, data: null, error: errorMessage(err), at: null });
    } finally {
      if (seq === regimeSeqRef.current) setRegimeLoading(false);
    }
  }, [instrument, contextRegime]);

  usePolling(fetchMi, MI_POLL_MS);
  // The shared summary leg owns the NIFTY diagnosis; only poll the direct
  // endpoint when the context cannot supply it.
  usePolling(fetchRegime, REGIME_POLL_MS, !contextRegime);

  // Adopt a fresh shared regime immediately (poll ticks would lag up to 15s).
  useEffect(() => {
    if (!contextRegime) return;
    regimeSeqRef.current += 1; // drop any in-flight direct response
    const usable = isUsableRegimeOverview(contextRegime, instrument) ? contextRegime : null;
    setRegimeState({
      instrument,
      data: usable,
      error: usable ? null : `No usable regime diagnosis returned for ${instrument}`,
      at: Date.now(),
    });
    setRegimeLoading(false);
  }, [contextRegime, instrument]);

  const prevInstrumentRef = useRef(instrument);
  useEffect(() => {
    if (prevInstrumentRef.current === instrument) return;
    prevInstrumentRef.current = instrument;
    miSeqRef.current += 1; // drop any in-flight response for the old symbol
    regimeSeqRef.current += 1;
    void fetchMi();
    void fetchRegime();
  }, [instrument, fetchMi, fetchRegime]);

  const currentMi = miState && miState.instrument === instrument ? miState : null;
  const currentRegime = regimeState && regimeState.instrument === instrument ? regimeState : null;
  const mi = currentMi?.data ?? null;
  const miError = currentMi?.error ?? null;
  const miStatus: IntelHubValue['miStatus'] = mi ? 'ready' : miError ? 'error' : 'loading';

  const value = useMemo<IntelHubValue>(
    () => ({
      instrument,
      mi,
      miError,
      miStatus,
      miUpdatedAt: currentMi?.at ?? null,
      regime: currentRegime?.data ?? null,
      regimeError: currentRegime?.error ?? null,
      regimeLoading,
    }),
    [instrument, mi, miError, miStatus, currentMi?.at, currentRegime, regimeLoading],
  );

  return <IntelHubContext.Provider value={value}>{children}</IntelHubContext.Provider>;
};

export function useIntelHub(): IntelHubValue {
  const ctx = useContext(IntelHubContext);
  if (!ctx) {
    throw new Error('useIntelHub must be used within an IntelHubProvider');
  }
  return ctx;
}

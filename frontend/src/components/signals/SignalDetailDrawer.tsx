'use client';

/**
 * SignalDetailDrawer (consolidated dossier drawer)
 *
 * Institutional detail view for one live, pending, or executed signal.
 * Serves both the War Room and the Signals Desk.
 *
 * Features:
 * - Radix-free fixed drawer with accessible backdrop, Esc key support, and Tab focus trap.
 * - Deep-dive levels (Entry range, Trigger, Stop loss, Target 1, Target 2, Risk points, R:R).
 * - Position sizing preview (1L and 5L accounts) + paper margin preview check (api.previewPaperMargin).
 * - Confluence scores breakdown.
 * - Explain rules (headline, bullets, strategy rules, invalidation conditions).
 * - Option contract preview.
 * - FSM lifecycle & state history.
 * - Execution & P&L auditing (when audit ledger record is present).
 * - On-demand AI trade setup validation & Deep Insight synthesis.
 */

import { memo, useState, useEffect, useCallback, useRef } from 'react';
import { api } from '@/lib/api';
import { fmtINR, fmtNum, fmtPct01, fmtSigned, TelemetryStrip, TelemetryItem, normalizeDirection } from '@/components/ui/desk';
import { parseCalibration, type CalibrationSummaryRow } from '@/components/research-lab/contracts';
import type { ExpectedMoveData } from '@/components/options/ExpectedMoveCard';
import { fmtTimeMs, fmtDateTimeMs, type ActiveRow } from './signalsNormalize';
import type { StandardActiveSignal } from '@/hooks/useActiveSignals';
import { X, RefreshCw, ExternalLink } from 'lucide-react';

export interface SignalDetailDrawerProps {
  signal?: {
    id: string;
    instrument?: string;
    direction?: string;
    strategy?: string;
    entry?: number;
    stopLoss?: number;
    target1?: number;
    target2?: number;
    confidence?: number;
    status?: string;
    contract?: string;
    timestamp?: number | string;
  } | ActiveRow | StandardActiveSignal | null;
  /** Backward compatibility for callers passing signalId directly (e.g. Signals Desk) */
  signalId?: string | null;
  isOpen?: boolean;
  onClose: () => void;
  /** Feed state label (e.g. LIVE, SYNCING, CLOSED), shown on the snapshot line. */
  feedState?: string | null;
}

interface DeepDiveLevels {
  entry_range?: unknown;
  trigger?: unknown;
  stop_loss?: unknown;
  target_1?: unknown;
  target_2?: unknown;
  risk_points?: unknown;
  risk_reward_t1?: unknown;
  risk_reward_t2?: unknown;
}

interface DeepDive {
  levels?: DeepDiveLevels | null;
  position_sizing_preview?: Record<string, unknown> | null;
  confluence?: unknown;
  explain?: unknown;
  option_contract?: unknown;
  fsm_history?: unknown;
  current_market_price?: unknown;
  timestamp_ms?: unknown;
  signal?: Record<string, unknown> | null;
}

interface FeedStatus {
  active_count?: unknown;
  confirmed_count?: unknown;
  armed_count?: unknown;
}

interface MarginPreview {
  required_margin?: unknown;
  premium?: unknown;
  available_margin?: unknown;
  affordable?: unknown;
}

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function asNum(v: unknown): number | null {
  if (v === null || v === undefined || v === '') return null;
  const n = typeof v === 'string' ? Number(v) : (v as number);
  return typeof n === 'number' && Number.isFinite(n) ? n : null;
}

function asStr(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  const s = String(v).trim();
  return s ? s : null;
}

function asObj(v: unknown): Record<string, unknown> | null {
  if (v && typeof v === 'object' && !Array.isArray(v)) return v as Record<string, unknown>;
  return null;
}

function fmtVal(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'number') return fmtNum(v, 2);
  if (typeof v === 'boolean') return v ? 'yes' : 'no';
  if (typeof v === 'string') {
    const s = v.trim();
    if (!s) return '—';
    return s.length > 140 ? `${s.slice(0, 140)}…` : s;
  }
  if (Array.isArray(v)) {
    const parts = v
      .filter((x) => typeof x === 'string' || typeof x === 'number' || typeof x === 'boolean')
      .map((x) => String(x));
    const joined = parts.slice(0, 6).join(', ');
    if (!joined) return '—';
    return joined.length > 140 ? `${joined.slice(0, 140)}…` : joined;
  }
  return '—';
}

function prettyKey(s: string): string {
  return s.replace(/_/g, ' ');
}

function pickMs(o: Record<string, unknown>, ...keys: string[]): number | null {
  for (const k of keys) {
    const v = o[k];
    if (typeof v === 'number' && Number.isFinite(v)) {
      return v < 1e12 ? Math.round(v * 1000) : Math.round(v);
    }
    if (typeof v === 'string' && v.trim()) {
      const t = new Date(v).getTime();
      if (Number.isFinite(t)) return t;
    }
  }
  return null;
}

function asStringArray(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.filter((x): x is string => typeof x === 'string' && x.trim() !== '');
}

/** Trade-audit decision → chip tone */
function validationTone(decision: unknown): string {
  const d = typeof decision === 'string' ? decision.toUpperCase() : '';
  if (d === 'CONFIRM') return 'chip--up';
  if (d === 'REJECT') return 'chip--down';
  return 'chip--warn';
}

function explainHeadline(explain: unknown): string | null {
  if (typeof explain === 'string') return null;
  const o = asObj(explain);
  if (!o) return null;
  return asStr(o['headline'] ?? o['summary'] ?? o['verdict'] ?? o['narrative'] ?? null);
}

function explainBullets(explain: unknown): string[] {
  if (typeof explain === 'string') return explain.trim() ? [explain.trim()] : [];
  const o = asObj(explain);
  if (!o) return [];
  const keys = ['reasons', 'bullets', 'factors', 'notes', 'observations', 'drivers', 'summary_points'];
  for (const k of keys) {
    const v = o[k];
    if (!Array.isArray(v)) continue;
    const out: string[] = [];
    for (const item of v) {
      if (typeof item === 'string' && item.trim()) out.push(item.trim());
      else if (item && typeof item === 'object') {
        const rec = item as Record<string, unknown>;
        const t = asStr(rec['text'] ?? rec['reason'] ?? null);
        if (t) out.push(t);
      }
      if (out.length >= 8) break;
    }
    if (out.length > 0) return out;
  }
  return [];
}

/**
 * Suggested paper quantity for the margin check: 1L sizing first, else one lot.
 * Null when backend publishes no lot size (never fabricate a quantity).
 */
function suggestedQty(dive: DeepDive | null): number | null {
  const sizing = asObj(dive?.position_sizing_preview);
  const oneL = asObj(sizing?.['account_1lakh']);
  const contract = asObj(dive?.option_contract);
  const lotSize = asNum(oneL?.['lot_size']) ?? asNum(contract?.['lot_size']);
  const qty = asNum(oneL?.['quantity']);
  if (qty !== null && qty > 0) return Math.round(qty);
  const lots = asNum(oneL?.['lots']);
  if (lots !== null && lots > 0 && lotSize !== null && lotSize > 0) return Math.round(lots * lotSize);
  return lotSize !== null && lotSize > 0 ? lotSize : null;
}

function toSizing(label: string, raw: unknown) {
  const o = asObj(raw);
  return {
    label,
    lots: o ? fmtVal(o['lots']) : '—',
    qty: o ? fmtVal(o['quantity']) : '—',
    risk: o ? fmtINR(asNum(o['risk_capital'])) : '—',
    allowed: o && typeof o['allowed'] === 'boolean' ? (o['allowed'] as boolean) : null,
    reason: o ? asStr(o['reason']) : null,
  };
}

export const SignalDetailDrawer = memo(function SignalDetailDrawer({
  signal,
  signalId: propSignalId,
  isOpen: propIsOpen,
  onClose,
  feedState,
}: SignalDetailDrawerProps) {
  const [dive, setDive] = useState<DeepDive | null>(null);
  const [audit, setAudit] = useState<Record<string, unknown> | null>(null);
  const [status, setStatus] = useState<FeedStatus | null>(null);
  const [margin, setMargin] = useState<MarginPreview | null>(null);
  const [marginQty, setMarginQty] = useState<number | null>(null);
  const [marginNote, setMarginNote] = useState<string | null>(null);
  const [marginLoading, setMarginLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Lazy model & risk context (ML calibration + options-intelligence expected move)
  const [mlContext, setMlContext] = useState<CalibrationSummaryRow | null>(null);
  const [mlContextLoading, setMlContextLoading] = useState(false);
  const [mlContextError, setMlContextError] = useState<string | null>(null);
  const [moveContext, setMoveContext] = useState<ExpectedMoveData | null>(null);
  const [moveContextLoading, setMoveContextLoading] = useState(false);
  const [moveContextError, setMoveContextError] = useState<string | null>(null);

  const drawerRef = useRef<HTMLDivElement | null>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const requestIdRef = useRef(0);
  const validationReqRef = useRef(0);
  const insightReqRef = useRef(0);
  const mlContextReqRef = useRef(0);
  const moveContextReqRef = useRef(0);

  // On-demand AI validation state
  const [validating, setValidating] = useState(false);
  const [validationResult, setValidationResult] = useState<any | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  // On-demand Deep Insight state
  const [deepInsightLoading, setDeepInsightLoading] = useState(false);
  const [deepInsightData, setDeepInsightData] = useState<any | null>(null);
  const [deepInsightError, setDeepInsightError] = useState<string | null>(null);

  // Normalize effective signal ID and properties
  const sigObj = (signal ?? null) as Record<string, unknown> | null;
  const effectiveId = asStr(sigObj?.id ?? sigObj?.signal_id ?? propSignalId);

  // If isOpen is explicitly passed, obey it; otherwise open when effectiveId or signal is present
  const isDrawerOpen = propIsOpen !== undefined ? propIsOpen : Boolean(effectiveId);

  // Normalized properties from prop signal, deep-dive signal, or audit
  const deepSig = asObj(dive?.signal);
  const auditSig = audit ?? null;

  const symbol =
    asStr(sigObj?.instrument ?? sigObj?.symbol ?? sigObj?.underlying) ??
    asStr(deepSig?.underlying ?? deepSig?.instrument) ??
    asStr(auditSig?.underlying) ??
    '—';

  const contract =
    asStr(sigObj?.contract) ??
    asStr((sigObj?.option_contract as any)?.broker_symbol) ??
    asStr((dive?.option_contract as any)?.broker_symbol) ??
    asStr((auditSig?.option_contract as any)?.broker_symbol) ??
    asStr(auditSig?.option_symbol);

  const directionRaw =
    asStr(sigObj?.direction) ??
    asStr(deepSig?.direction) ??
    asStr(auditSig?.direction) ??
    'BUY';
  const directionNorm = normalizeDirection(directionRaw);
  const direction: 'BUY' | 'SELL' = directionNorm === 'BEARISH' ? 'SELL' : 'BUY';

  const strategy =
    asStr(sigObj?.strategy) ??
    asStr(deepSig?.strategy) ??
    asStr(auditSig?.strategy) ??
    '—';

  const entry =
    asNum(sigObj?.entry) ??
    asNum(sigObj?.trigger) ??
    asNum((sigObj as any)?.entryFill) ??
    asNum(dive?.levels?.trigger) ??
    asNum(deepSig?.entry_price) ??
    asNum(deepSig?.trigger) ??
    asNum(auditSig?.actual_fill_price);

  const stopLoss =
    asNum(sigObj?.stopLoss) ??
    asNum((sigObj as any)?.sl) ??
    asNum(sigObj?.stop_loss) ??
    asNum(dive?.levels?.stop_loss) ??
    asNum(deepSig?.stop_loss) ??
    asNum(auditSig?.stop_loss);

  const target1 =
    asNum(sigObj?.target1) ??
    asNum((sigObj as any)?.t1) ??
    asNum(sigObj?.target_1) ??
    asNum(dive?.levels?.target_1) ??
    asNum(deepSig?.target_1) ??
    asNum(auditSig?.target_1);

  const target2 =
    asNum(sigObj?.target2) ??
    asNum((sigObj as any)?.t2) ??
    asNum(sigObj?.target_2) ??
    asNum(dive?.levels?.target_2) ??
    asNum(deepSig?.target_2) ??
    asNum(auditSig?.target_2);

  const confidenceRaw =
    asNum(sigObj?.confidence) ??
    asNum((sigObj as any)?.confidence01 ? ((sigObj as any).confidence01 as number) * 100 : null) ??
    asNum(deepSig?.confidence) ??
    asNum(auditSig?.confidence);
  const confidence =
    confidenceRaw !== null
      ? confidenceRaw > 1
        ? Math.round(confidenceRaw)
        : Math.round(confidenceRaw * 100)
      : null;

  const timestamp =
    pickMs(sigObj ?? {}, 'timestamp', 'timestamp_ms', 'timeMs', 'created_at_utc', 'created_at') ??
    pickMs(deepSig ?? {}, 'timestamp', 'timestamp_ms', 'created_at_utc', 'created_at') ??
    pickMs(auditSig ?? {}, 'executed_at_utc', 'timestamp_utc', 'created_at');

  const loadDossier = useCallback(async () => {
    if (!effectiveId) return;
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    setMargin(null);
    setMarginQty(null);
    setMarginNote(null);

    try {
      const [diveRes, statusRes, auditRes] = await Promise.allSettled([
        api.getSignalDeepDive(effectiveId),
        api.getSignalsStatus(),
        api.getSingleSignalAudit(effectiveId),
      ]);

      if (requestIdRef.current !== requestId) return;

      if (diveRes.status === 'fulfilled') {
        const dd = (diveRes.value ?? {}) as DeepDive;
        setDive(dd);

        // Affordability check against suggested sizing
        const qty = suggestedQty(dd);
        const activeEntry = entry ?? asNum(dd.levels?.trigger);
        const activeSymbol = contract ?? symbol;

        if (qty === null) {
          setMarginNote('margin preview unavailable — contract lot size not published');
        } else if (activeEntry !== null && activeSymbol && activeSymbol !== '—') {
          setMarginLoading(true);
          try {
            const pv = await api.previewPaperMargin({
              symbol: activeSymbol,
              underlying: symbol !== '—' && symbol ? symbol : activeSymbol,
              side: direction,
              quantity: qty,
              price: activeEntry,
            });
            if (requestIdRef.current !== requestId) return;
            setMargin((pv?.data ?? null) as MarginPreview | null);
            setMarginQty(qty);
          } catch {
            if (requestIdRef.current !== requestId) return;
            setMargin(null);
            setMarginQty(null);
            setMarginNote('margin preview unavailable');
          } finally {
            if (requestIdRef.current === requestId) setMarginLoading(false);
          }
        }
      } else {
        setDive(null);
        setError(diveRes.reason instanceof Error ? diveRes.reason.message : 'dossier unavailable');
      }

      if (statusRes.status === 'fulfilled') {
        setStatus(statusRes.value as FeedStatus);
      } else {
        setStatus(null);
      }

      if (auditRes.status === 'fulfilled') {
        const a = auditRes.value as Record<string, unknown> | null;
        if (a && typeof a === 'object' && !('__err' in a)) {
          setAudit(a);
        } else {
          setAudit(null);
        }
      } else {
        setAudit(null);
      }
    } catch (e) {
      if (requestIdRef.current === requestId) {
        setError(e instanceof Error ? e.message : 'dossier unavailable');
      }
    } finally {
      if (requestIdRef.current === requestId) setLoading(false);
    }
  }, [effectiveId, entry, contract, symbol, direction]);

  const handleValidate = useCallback(async () => {
    if (!symbol || symbol === '—' || entry === null) return;
    const requestId = ++validationReqRef.current;
    setValidating(true);
    setValidationError(null);
    try {
      const res = await api.validateTradeSetup({
        symbol,
        direction,
        entry_price: entry,
        stop_loss: stopLoss ?? entry,
        target_price: target1 ?? entry,
        timeframe: '5m',
      });
      if (validationReqRef.current !== requestId) return;
      setValidationResult(res?.data ?? res);
    } catch (e) {
      if (validationReqRef.current !== requestId) return;
      setValidationError(e instanceof Error ? e.message : 'Validation failed');
    } finally {
      if (validationReqRef.current === requestId) setValidating(false);
    }
  }, [symbol, direction, entry, stopLoss, target1]);

  const handleDeepInsight = useCallback(async () => {
    if (!symbol || symbol === '—') return;
    const requestId = ++insightReqRef.current;
    setDeepInsightLoading(true);
    setDeepInsightError(null);
    try {
      const res = await api.getDeepInsight(symbol);
      if (insightReqRef.current !== requestId) return;
      setDeepInsightData(res?.data ?? res);
    } catch (e) {
      if (insightReqRef.current !== requestId) return;
      setDeepInsightError(e instanceof Error ? e.message : 'Deep insight unavailable');
    } finally {
      if (insightReqRef.current === requestId) setDeepInsightLoading(false);
    }
  }, [symbol]);

  const loadModelContext = useCallback(async () => {
    if (!effectiveId || !symbol || symbol === '—') return;
    const requestId = ++mlContextReqRef.current;
    setMlContextLoading(true);
    setMlContext(null);
    setMlContextError(null);
    try {
      const res = await api.getMLCalibration(symbol);
      if (mlContextReqRef.current !== requestId) return;
      const parsed = parseCalibration(asObj((res as Record<string, unknown> | null)?.data));
      if (!parsed) {
        setMlContext(null);
        setMlContextError('calibration summary not published');
        return;
      }
      setMlContext(parsed);
    } catch (e) {
      if (mlContextReqRef.current !== requestId) return;
      setMlContext(null);
      setMlContextError(e instanceof Error ? e.message : 'calibration unavailable');
    } finally {
      if (mlContextReqRef.current === requestId) setMlContextLoading(false);
    }
  }, [effectiveId, symbol]);

  const loadExpectedMove = useCallback(
    async (spot: number) => {
      if (!effectiveId || !symbol || symbol === '—') return;
      const requestId = ++moveContextReqRef.current;
      setMoveContextLoading(true);
      setMoveContext(null);
      setMoveContextError(null);
      try {
        const res = await api.projectExpectedMove({
          underlying: symbol,
          spot,
          direction,
          horizon: 'INTRADAY',
          ...(target1 !== null ? { structural_target: target1 } : {}),
        });
        if (moveContextReqRef.current !== requestId) return;
        const envelope = asObj(res);
        const rec = asObj(envelope?.['data']) ?? envelope;
        const spotPrice = asNum(rec?.['spot_price']);
        if (spotPrice === null || spotPrice <= 0) {
          setMoveContext(null);
          setMoveContextError('projection returned no spot price');
          return;
        }
        setMoveContext(rec as unknown as ExpectedMoveData);
      } catch (e) {
        if (moveContextReqRef.current !== requestId) return;
        setMoveContext(null);
        setMoveContextError(e instanceof Error ? e.message : 'expected move unavailable');
      } finally {
        if (moveContextReqRef.current === requestId) setMoveContextLoading(false);
      }
    },
    [effectiveId, symbol, direction, target1],
  );

  // Expected move anchors only on a published live mark (dossier/audit), never on a guess.
  useEffect(() => {
    if (!isDrawerOpen || !effectiveId) return;
    const spot = asNum(dive?.current_market_price) ?? asNum(audit?.current_price);
    if (spot === null || spot <= 0) return;
    void loadExpectedMove(spot);
  }, [isDrawerOpen, effectiveId, dive, audit, loadExpectedMove]);

  // Open / signal change: reset and load once
  useEffect(() => {
    if (!isDrawerOpen || !effectiveId) return;
    validationReqRef.current += 1;
    insightReqRef.current += 1;
    setDive(null);
    setAudit(null);
    setStatus(null);
    setMargin(null);
    setMarginQty(null);
    setMarginNote(null);
    setError(null);
    setValidationResult(null);
    setValidationError(null);
    setValidating(false);
    setDeepInsightData(null);
    setDeepInsightError(null);
    setDeepInsightLoading(false);
    mlContextReqRef.current += 1;
    moveContextReqRef.current += 1;
    setMlContext(null);
    setMlContextError(null);
    setMlContextLoading(false);
    setMoveContext(null);
    setMoveContextError(null);
    setMoveContextLoading(false);
    void loadDossier();
    void loadModelContext();
  }, [isDrawerOpen, effectiveId, loadDossier, loadModelContext]);

  // Handle Esc key to close & Tab focus trap
  useEffect(() => {
    if (!isDrawerOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }
      if (e.key === 'Tab') {
        const node = drawerRef.current;
        if (!node) return;
        const focusables = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
          (el) => !el.hasAttribute('disabled'),
        );
        if (focusables.length === 0) {
          e.preventDefault();
          node.focus();
          return;
        }
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = document.activeElement as HTMLElement | null;
        const inside = active !== null && node.contains(active);
        if (e.shiftKey && (!inside || active === first)) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && (!inside || active === last)) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isDrawerOpen, onClose]);

  // Initial focus into dialog and focus restore upon close
  useEffect(() => {
    if (!isDrawerOpen) return;
    restoreFocusRef.current = (document.activeElement as HTMLElement | null) ?? null;
    const node = drawerRef.current;
    if (node) {
      const first = node.querySelector<HTMLElement>(FOCUSABLE);
      (first ?? node).focus();
    }
    return () => {
      const restore = restoreFocusRef.current;
      if (restore && restore.isConnected && typeof restore.focus === 'function') {
        restore.focus();
      }
    };
  }, [isDrawerOpen]);

  if (!isDrawerOpen || !effectiveId) return null;

  const activeCount = asNum(status?.active_count);
  const confirmedCount = asNum(status?.confirmed_count);
  const statusPill = activeCount !== null ? `${activeCount} active · ${confirmedCount ?? '—'} confirmed` : null;

  const levels = dive?.levels ?? null;
  const entryRangeRaw: unknown[] = levels && Array.isArray(levels.entry_range) ? levels.entry_range : [];
  const rrT1 = asNum(levels?.risk_reward_t1);
  const rrT2 = asNum(levels?.risk_reward_t2);
  const levelRows: Array<[string, string]> = [
    ['Entry range', entryRangeRaw.length >= 2 ? `${fmtNum(entryRangeRaw[0], 1)} – ${fmtNum(entryRangeRaw[1], 1)}` : fmtNum(entry, 1)],
    ['Trigger', fmtNum(levels?.trigger ?? entry, 1)],
    ['Stop', fmtNum(levels?.stop_loss ?? stopLoss, 1)],
    ['Target 1', fmtNum(levels?.target_1 ?? target1, 1)],
    ['Target 2', target2 !== undefined && target2 !== null ? fmtNum(levels?.target_2 ?? target2, 1) : fmtNum(levels?.target_2 ?? null, 1)],
    ['Risk', fmtNum(levels?.risk_points ?? null, 1) === '—' ? '—' : `${fmtNum(levels?.risk_points ?? null, 1)} pts`],
    ['R:R to T1', rrT1 !== null ? `1 : ${fmtNum(rrT1, 1)}` : '—'],
    ['R:R to T2', rrT2 !== null ? `1 : ${fmtNum(rrT2, 1)}` : '—'],
  ];

  const sizingPrev = asObj(dive?.position_sizing_preview);
  const sizingRows = [
    toSizing('1L account', sizingPrev?.['account_1lakh']),
    toSizing('5L account', sizingPrev?.['account_5lakh']),
  ];

  const reqMargin = asNum(margin?.required_margin);
  const availMargin = asNum(margin?.available_margin);
  const premium = asNum(margin?.premium);
  const affordable = margin && typeof margin.affordable === 'boolean' ? (margin.affordable as boolean) : null;

  const confluenceObj = asObj(dive?.confluence);
  const confluenceRows: Array<[string, unknown]> = confluenceObj ? Object.entries(confluenceObj).slice(0, 12) : [];

  const headline = explainHeadline(dive?.explain);
  const bullets = explainBullets(dive?.explain);

  const contractObj = asObj(dive?.option_contract) ?? asObj(audit?.option_contract);
  const contractRows: Array<[string, unknown]> = contractObj ? Object.entries(contractObj).slice(0, 10) : [];

  const historyRaw: unknown[] = Array.isArray(dive?.fsm_history)
    ? dive.fsm_history
    : Array.isArray(audit?.state_history)
      ? audit.state_history
      : [];
  const historyRows = historyRaw
    .map(asObj)
    .filter((h): h is Record<string, unknown> => h !== null)
    .slice(0, 12)
    .map((h, i) => ({
      key: `${asStr(h['state'] ?? h['fsm_state'] ?? h['to_state'] ?? h['event']) ?? 'state'}-${i}`,
      state: asStr(h['state'] ?? h['fsm_state'] ?? h['to_state'] ?? h['event']) ?? '—',
      at: fmtDateTimeMs(pickMs(h, 'at_ms', 'at', 'timestamp_ms', 'processed_timestamp', 'created_at', 'timestamp_utc')),
      detail: asStr(h['reason'] ?? h['reason_code'] ?? h['detail'] ?? h['note'] ?? null) ?? '—',
    }));

  const markPrice = asNum(dive?.current_market_price) ?? asNum(audit?.current_price);

  // Model & risk context — every number comes from a published payload, never a guess.
  const mlOverall = mlContext?.overall ?? null;
  const mlHitRate = asNum(mlOverall?.hit_rate);
  const mlValue =
    mlOverall !== null && mlOverall.n > 0 && mlHitRate !== null
      ? `${fmtPct01(mlHitRate)} · n=${mlOverall.n}`
      : '—';
  const mlNote = mlContextError
    ? mlContextError
    : mlContext !== null && (mlContext.cells.length === 0 || mlOverall === null || mlOverall.n === 0)
      ? `no settled ML predictions for ${symbol} yet`
      : mlOverall !== null && mlOverall.n < 30
        ? 'n<30 — hit rate is statistical noise'
        : null;

  const movePoints = asNum(moveContext?.expected_move_points);
  const moveValue = movePoints !== null ? `±${fmtNum(movePoints, 1)} pts` : '—';
  const moveParts: string[] = [];
  if (moveContext) {
    const t1Pts = asNum(moveContext.conservative_move_points);
    const t2Pts = asNum(moveContext.aggressive_move_points);
    const velocity = asNum(moveContext.expected_velocity_pts_per_hour);
    if (t1Pts !== null) moveParts.push(`T1 ${fmtNum(t1Pts, 1)} pts`);
    if (t2Pts !== null) moveParts.push(`T2 ${fmtNum(t2Pts, 1)} pts`);
    if (velocity !== null) moveParts.push(`${fmtSigned(velocity, 1)} pts/h`);
  }
  const moveNote = moveContextError
    ? moveContextError
    : moveContext === null && !moveContextLoading
      ? markPrice === null
        ? 'live mark unavailable — projection not attempted'
        : 'projection unavailable'
      : moveContext !== null && movePoints === null
        ? 'projection published no move magnitude'
        : null;

  // Execution & P&L audit fields (if executed)
  const fillPrice = asNum(audit?.actual_fill_price ?? audit?.fill_price);
  const fillQty = asNum(audit?.quantity ?? audit?.qty);
  const orderId = asStr(audit?.paper_order_id ?? audit?.order_id);
  const realizedPnl = asNum(audit?.actual_pnl_inr ?? audit?.realized_pnl);
  const unrealizedPnl = asNum(audit?.unrealized_pnl_inr);
  const exitPrice = asNum(audit?.exit_price);

  return (
    <div
      className="fixed inset-0 z-[55] flex justify-end bg-foreground/40 backdrop-blur-2xs transition-opacity animate-in fade-in"
      onClick={onClose}
      role="presentation"
    >
      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label={`Signal dossier ${contract ?? effectiveId}`}
        className="w-full max-w-2xl h-full bg-card border-l border-border-strong flex flex-col overflow-hidden"
        style={{ boxShadow: 'var(--ds-shadow-lg)' }}
        onClick={(e) => e.stopPropagation()}
        tabIndex={-1}
      >
        {/* Header */}
        <div className="p-3.5 border-b border-border flex items-center justify-between gap-3 bg-surface-subtle">
          <div className="flex items-center gap-2.5">
            <h2 className="text-[13px] font-semibold tracking-normal text-foreground">Signal dossier</h2>
            <span className="chip chip--info num">
              {contract ?? effectiveId}
            </span>
            {statusPill ? (
              <span className="chip chip--neut num">
                {statusPill}
              </span>
            ) : null}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void loadDossier()}
              disabled={loading}
              title="Refresh dossier"
              aria-label="Refresh dossier"
              className="p-1.5 rounded border border-border-strong bg-card hover:bg-surface-subtle text-muted-foreground shadow-2xs cursor-pointer"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>

            <button
              type="button"
              onClick={onClose}
              title="Close (Esc)"
              aria-label="Close dossier"
              className="p-1.5 rounded border border-border-strong bg-card hover:bg-surface-subtle text-muted-foreground shadow-2xs cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-3" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div role="note" className="notice notice--info" style={{ fontSize: 12 }}>
            execution wiring pending — this dossier is read-only in this phase.
          </div>

          {error ? (
            <div
              role="alert"
              className="p-3 mb-2 rounded-md border border-down-line bg-down-wash flex items-center justify-between gap-3 text-xs"
            >
              <div className="flex items-center gap-2">
                <span className="font-semibold text-down-strong">Error loading dossier:</span>
                <span className="text-down">{error}</span>
              </div>
              <button
                type="button"
                onClick={() => void loadDossier()}
                className="px-2.5 py-1 rounded bg-card border border-down-line font-semibold text-down-strong hover:bg-down-wash cursor-pointer"
              >
                Retry
              </button>
            </div>
          ) : null}

          {loading && !dive && !audit ? (
            <div className="space-y-2" aria-label="Loading dossier">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-8 rounded bg-muted animate-pulse" />
              ))}
            </div>
          ) : (
            <>
              {/* Snapshot */}
              <section className="card" aria-label="Snapshot">
                <div className="card-hd">
                  <h3 className="card-title">Snapshot</h3>
                  {timestamp !== null ? <span className="card-meta num">{fmtTimeMs(timestamp)}</span> : null}
                </div>
                <div className="card-bd" style={{ padding: 0 }}>
                  <TelemetryStrip>
                    <TelemetryItem
                      label="Side"
                      value={direction}
                      tone={direction === 'BUY' ? 'bull' : 'bear'}
                    />
                    <TelemetryItem label="Entry" value={<span className="num">{fmtNum(entry, 1)}</span>} />
                    <TelemetryItem label="Stop" value={<span className="num">{fmtNum(stopLoss, 1)}</span>} />
                    <TelemetryItem label="Target" value={<span className="num">{fmtNum(target1, 1)}</span>} />
                    <TelemetryItem label="Confidence" value={<span className="num">{confidence !== null ? `${confidence}%` : '—'}</span>} />
                    {markPrice !== null ? (
                      <TelemetryItem label="Mark" value={<span className="num">{fmtNum(markPrice, 1)}</span>} />
                    ) : null}
                    <TelemetryItem label="Feed" value={feedState ?? '—'} />
                  </TelemetryStrip>
                  <p className="muted" style={{ margin: 0, padding: '6px 12px 8px', fontSize: 12 }}>
                    {strategy} · {symbol} {timestamp !== null ? `· snapshot ${fmtTimeMs(timestamp)}` : ''}
                  </p>
                </div>
              </section>

              {/* Levels */}
              <section className="card" aria-label="Levels">
                <div className="card-hd">
                  <h3 className="card-title">Levels</h3>
                </div>
                <div className="card-bd" style={{ padding: 0 }}>
                  <div className="tbl-wrap" style={{ border: 0 }}>
                    <table className="tbl tbl-dense">
                      <tbody>
                        {levelRows.map(([label, value]) => (
                          <tr key={label}>
                            <td style={{ color: 'var(--ds-text-secondary)' }}>{label}</td>
                            <td className="r num">{value}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </section>

              {/* Position sizing & Margin preview */}
              <section className="card" aria-label="Position sizing">
                <div className="card-hd">
                  <h3 className="card-title">Position sizing</h3>
                </div>
                <div className="card-bd" style={{ padding: 0 }}>
                  <div className="tbl-wrap" style={{ border: 0 }}>
                    <table className="tbl tbl-dense">
                      <thead>
                        <tr>
                          <th scope="col">Account</th>
                          <th scope="col" className="r">Lots</th>
                          <th scope="col" className="r">Qty</th>
                          <th scope="col" className="r">Risk</th>
                          <th scope="col">State</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sizingRows.map((row) => (
                          <tr key={row.label}>
                            <td style={{ color: 'var(--ds-text-secondary)' }}>{row.label}</td>
                            <td className="r num">{row.lots}</td>
                            <td className="r num">{row.qty}</td>
                            <td className="r num">{row.risk}</td>
                            <td>
                              {row.allowed === null ? (
                                <span className="muted">—</span>
                              ) : row.allowed ? (
                                <span className="chip chip--up" title={row.reason ?? undefined}>sized</span>
                              ) : (
                                <span className="chip chip--warn" title={row.reason ?? undefined}>check size</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div style={{ padding: '8px 12px', borderTop: '1px solid var(--ds-border-subtle)', fontSize: 12, color: 'var(--ds-text-secondary)' }}>
                    {marginLoading ? (
                      <span>checking margin…</span>
                    ) : margin ? (
                      <span className="num">
                        margin check{marginQty !== null ? ` for ${marginQty} units` : ''} · required {fmtINR(reqMargin)} · premium {fmtINR(premium)} · available {fmtINR(availMargin)}{' '}
                        {affordable === true ? (
                          <span className="chip chip--up">fits margin</span>
                        ) : affordable === false ? (
                          <span className="chip chip--warn">short of margin</span>
                        ) : null}
                      </span>
                    ) : (
                      <span>{marginNote ?? 'margin preview unavailable'}</span>
                    )}
                  </div>
                </div>
              </section>

              {/* Model & risk context */}
              <section className="card" aria-label="Model and risk context">
                <div className="card-hd">
                  <h3 className="card-title">Model &amp; risk context</h3>
                  <span className="card-meta">{symbol}</span>
                </div>
                <div className="card-bd" style={{ padding: 0 }}>
                  <div className="tbl-wrap" style={{ border: 0 }}>
                    <table className="tbl tbl-dense">
                      <tbody>
                        <tr>
                          <td style={{ color: 'var(--ds-text-secondary)' }}>ML calibration</td>
                          <td className="r num">{mlValue}</td>
                        </tr>
                        <tr>
                          <td style={{ color: 'var(--ds-text-secondary)' }}>Expected move · 1h</td>
                          <td className="r num">{moveValue}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <div
                    style={{
                      padding: '8px 12px',
                      borderTop: '1px solid var(--ds-border-subtle)',
                      fontSize: 11.5,
                      color: 'var(--ds-text-secondary)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 4,
                    }}
                  >
                    {mlContextLoading || moveContextLoading ? <span>loading model context…</span> : null}
                    {!mlContextLoading && mlNote ? <span>ML calibration — {mlNote}</span> : null}
                    {!moveContextLoading && moveNote ? <span>Expected move — {moveNote}</span> : null}
                    {moveParts.length > 0 ? <span className="num">{moveParts.join(' · ')}</span> : null}
                  </div>
                </div>
              </section>

              {/* Confluence */}
              <section className="card" aria-label="Confluence">
                <div className="card-hd">
                  <h3 className="card-title">Confluence</h3>
                </div>
                <div className="card-bd" style={{ padding: 0 }}>
                  {confluenceRows.length === 0 ? (
                    <p className="muted" style={{ margin: 0, padding: '8px 12px', fontSize: 12 }}>confluence breakdown unavailable</p>
                  ) : (
                    <div className="tbl-wrap" style={{ border: 0 }}>
                      <table className="tbl tbl-dense">
                        <tbody>
                          {confluenceRows.map(([k, v]) => (
                            <tr key={k}>
                              <td style={{ color: 'var(--ds-text-secondary)' }}>{prettyKey(k)}</td>
                              <td className="r num">{fmtVal(v)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </section>

              {/* Why this signal / Explain rules */}
              <section className="card" aria-label="Why this signal">
                <div className="card-hd">
                  <h3 className="card-title">Why this signal</h3>
                </div>
                <div className="card-bd">
                  {headline ? <p style={{ margin: '0 0 6px', fontSize: 12.5 }}>{headline}</p> : null}
                  {bullets.length === 0 ? (
                    <p className="muted" style={{ margin: 0, fontSize: 12 }}>explain bundle unavailable</p>
                  ) : (
                    <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12.5, display: 'flex', flexDirection: 'column', gap: 4 }}>
                      {bullets.map((b, i) => (
                        <li key={i}>{b}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </section>

              {/* Option contract */}
              <section className="card" aria-label="Option contract">
                <div className="card-hd">
                  <h3 className="card-title">Option contract</h3>
                </div>
                <div className="card-bd" style={{ padding: 0 }}>
                  {contractRows.length === 0 ? (
                    <p className="muted" style={{ margin: 0, padding: '8px 12px', fontSize: 12 }}>no option contract on this signal</p>
                  ) : (
                    <div className="tbl-wrap" style={{ border: 0 }}>
                      <table className="tbl tbl-dense">
                        <tbody>
                          {contractRows.map(([k, v]) => (
                            <tr key={k}>
                              <td style={{ color: 'var(--ds-text-secondary)' }}>{prettyKey(k)}</td>
                              <td className="r num">{fmtVal(v)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </section>

              {/* Execution & P&L (if executed order exists) */}
              {fillPrice !== null ? (
                <section className="card" aria-label="Execution and P&L">
                  <div className="card-hd">
                    <h3 className="card-title">Execution &amp; P&amp;L</h3>
                  </div>
                  <div className="card-bd" style={{ padding: 0 }}>
                    <div className="tbl-wrap" style={{ border: 0 }}>
                      <table className="tbl tbl-dense">
                        <tbody>
                          <tr>
                            <td style={{ color: 'var(--ds-text-secondary)' }}>Fill Price</td>
                            <td className="r num">{fmtINR(fillPrice)} {fillQty !== null ? `× ${fillQty}` : ''}</td>
                          </tr>
                          {orderId ? (
                            <tr>
                              <td style={{ color: 'var(--ds-text-secondary)' }}>Order ID</td>
                              <td className="r num">{orderId.slice(0, 18)}</td>
                            </tr>
                          ) : null}
                          {exitPrice !== null ? (
                            <tr>
                              <td style={{ color: 'var(--ds-text-secondary)' }}>Exit Price</td>
                              <td className="r num">{fmtINR(exitPrice)}</td>
                            </tr>
                          ) : null}
                          {realizedPnl !== null ? (
                            <tr>
                              <td style={{ color: 'var(--ds-text-secondary)' }}>Realized P&amp;L</td>
                              <td className={`r num ${realizedPnl >= 0 ? 'text-bull-strong' : 'text-bear-strong'}`}>
                                {realizedPnl >= 0 ? '+' : ''}{fmtINR(realizedPnl)}
                              </td>
                            </tr>
                          ) : null}
                          {unrealizedPnl !== null ? (
                            <tr>
                              <td style={{ color: 'var(--ds-text-secondary)' }}>Unrealized (Live)</td>
                              <td className={`r num ${unrealizedPnl >= 0 ? 'text-bull-strong' : 'text-bear-strong'}`}>
                                {unrealizedPnl >= 0 ? '+' : ''}{fmtINR(unrealizedPnl)}
                              </td>
                            </tr>
                          ) : null}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </section>
              ) : null}

              {/* State history / FSM history */}
              <section className="card" aria-label="State history">
                <div className="card-hd">
                  <h3 className="card-title">State history</h3>
                </div>
                <div className="card-bd" style={{ padding: 0 }}>
                  {historyRows.length === 0 ? (
                    <p className="muted" style={{ margin: 0, padding: '8px 12px', fontSize: 12 }}>no state transitions recorded</p>
                  ) : (
                    <div className="tbl-wrap" style={{ border: 0 }}>
                      <table className="tbl tbl-dense">
                        <thead>
                          <tr>
                            <th scope="col">State</th>
                            <th scope="col">At</th>
                            <th scope="col">Detail</th>
                          </tr>
                        </thead>
                        <tbody>
                          {historyRows.map((row) => (
                            <tr key={row.key}>
                              <td>{row.state}</td>
                              <td className="num">{row.at}</td>
                              <td style={{ color: 'var(--ds-text-secondary)' }}>{row.detail}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </section>

              {/* AI Second Opinion (On-Demand) */}
              <section className="card" aria-label="AI Second Opinion">
                <div className="card-hd flex justify-between items-center" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h3 className="card-title">AI Second Opinion (On-Demand)</h3>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button
                      type="button"
                      onClick={handleValidate}
                      disabled={validating || entry === null}
                      className="btn"
                      style={{ fontSize: 11, padding: '2px 8px' }}
                      title="Run AI trade setup validation against options walls and regime"
                    >
                      {validating ? 'Auditing…' : 'Validate Setup'}
                    </button>
                    <button
                      type="button"
                      onClick={handleDeepInsight}
                      disabled={deepInsightLoading}
                      className="btn"
                      style={{ fontSize: 11, padding: '2px 8px' }}
                      title="Fetch AI Deep Insight synthesis for this instrument"
                    >
                      {deepInsightLoading ? 'Synthesizing…' : 'Deep Insight'}
                    </button>
                  </div>
                </div>
                <div className="card-bd" style={{ padding: '10px 14px' }}>
                  {validationError && (
                    <p className="text-bear-strong text-xs m-0 mb-2" style={{ color: 'var(--ds-bear-strong)', fontSize: 11.5, margin: '0 0 6px' }}>{validationError}</p>
                  )}
                  {deepInsightError && (
                    <p className="text-bear-strong text-xs m-0 mb-2" style={{ color: 'var(--ds-bear-strong)', fontSize: 11.5, margin: '0 0 6px' }}>{deepInsightError}</p>
                  )}

                  {validationResult && (
                    <div className="p-3 rounded bg-surface-subtle border border-border mb-3 space-y-2 num" style={{ padding: 8, background: 'var(--ds-surface-subtle)', borderRadius: 4, marginBottom: 8 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontWeight: 600, fontSize: 12 }}>Setup audit verdict</span>
                        <span className={`chip ${validationTone(validationResult.decision)}`}>
                          {typeof validationResult.decision === 'string' ? validationResult.decision : 'UNKNOWN'}
                        </span>
                      </div>
                      {typeof validationResult.score === 'number' && Number.isFinite(validationResult.score) ? (
                        <div style={{ fontSize: 11.5, color: 'var(--ds-text-secondary)', marginTop: 4 }}>
                          Score: <span style={{ fontWeight: 600, color: 'var(--ds-ink)' }}>{Math.round(validationResult.score)}/100</span>
                          {typeof validationResult.risk_reward_calculated === 'number' && Number.isFinite(validationResult.risk_reward_calculated)
                            ? ` · R:R ${fmtNum(validationResult.risk_reward_calculated, 1)}`
                            : ''}
                        </div>
                      ) : null}
                      {typeof validationResult.executive_verdict === 'string' && validationResult.executive_verdict.trim() ? (
                        <p style={{ fontSize: 11.5, color: 'var(--ds-text-secondary)', margin: '4px 0 0', whiteSpace: 'pre-wrap' }}>
                          {validationResult.executive_verdict}
                        </p>
                      ) : null}
                      {[
                        ['Technical', validationResult.technical_alignment],
                        ['Derivatives', validationResult.derivatives_alignment],
                        ['Volatility', validationResult.volatility_regime_check],
                      ]
                        .filter(([, v]) => typeof v === 'string' && v.trim() !== '')
                        .map(([label, v]) => (
                          <div key={label} style={{ fontSize: 11, color: 'var(--ds-text-secondary)' }}>
                            <span style={{ fontWeight: 600, color: 'var(--ds-ink-2)' }}>{label}:</span> {String(v)}
                          </div>
                        ))}
                      {asStringArray(validationResult.warning_traps).length > 0 ? (
                        <div>
                          <span className="micro-label" style={{ display: 'block', fontSize: 10, marginTop: 4 }}>Warning traps</span>
                          <ul style={{ margin: '2px 0 0', paddingLeft: 16, fontSize: 11.5, color: 'var(--ds-warn-strong)' }}>
                            {asStringArray(validationResult.warning_traps).map((t, i) => <li key={i}>{t}</li>)}
                          </ul>
                        </div>
                      ) : null}
                      {asStringArray(validationResult.invalidation_conditions).length > 0 ? (
                        <div>
                          <span className="micro-label" style={{ display: 'block', fontSize: 10, marginTop: 4 }}>Invalidation conditions</span>
                          <ul style={{ margin: '2px 0 0', paddingLeft: 16, fontSize: 11.5, color: 'var(--ds-text-secondary)' }}>
                            {asStringArray(validationResult.invalidation_conditions).map((t, i) => <li key={i}>{t}</li>)}
                          </ul>
                        </div>
                      ) : null}
                    </div>
                  )}

                  {deepInsightData && (
                    <div style={{ padding: 8, background: 'var(--ds-surface-subtle)', borderRadius: 4 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                        <span style={{ fontWeight: 600, fontSize: 12 }}>Deep Insight Synthesis</span>
                        <span className="chip chip--info">AI Synthesized</span>
                      </div>
                      <p style={{ fontSize: 11.5, color: 'var(--ds-text-secondary)', margin: 0, whiteSpace: 'pre-wrap' }}>
                        {deepInsightData.executive_summary ?? deepInsightData.summary ?? deepInsightData.content ?? JSON.stringify(deepInsightData, null, 2)}
                      </p>
                    </div>
                  )}

                  {!validationResult && !deepInsightData && !validating && !deepInsightLoading && (
                    <p className="muted" style={{ fontSize: 12, margin: 0 }}>
                      Click &quot;Validate Setup&quot; to audit entry/stop against options walls, or &quot;Deep Insight&quot; for AI multi-horizon thesis.
                    </p>
                  )}
                </div>
              </section>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-border bg-surface-subtle flex items-center justify-between text-xs text-ink-3 font-mono">
          <span>Press Esc or click close to return</span>
          <a
            href="/signals"
            className="flex items-center gap-1 text-accent-strong font-semibold hover:underline"
          >
            <span>Full Signals desk</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>
    </div>
  );
});

export { SignalDetailDrawer as SignalDossierDrawer };
export default SignalDetailDrawer;

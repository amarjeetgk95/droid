'use client';

import { memo, useState, useEffect, useCallback, useRef, Fragment } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { api } from '@/lib/api';
import type {
  InstitutionalFlowResponse,
  MaxPainResult,
  OptionChainResponse,
  OptionChainStrikeRow,
} from '@/lib/types';
import { fmtINR, fmtNum } from '@/components/ui/desk';
import { X, RefreshCw, ExternalLink, ChevronDown } from 'lucide-react';

type DrawerDirection = 'BULLISH' | 'BEARISH' | 'NEUTRAL';
type DrawerTab = 'quotes' | 'flow' | 'picker' | 'whatif';

interface OptionsChainDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  instrument: string;
  direction?: DrawerDirection;
}

const TABS: { id: DrawerTab; label: string }[] = [
  { id: 'quotes', label: 'Quotes' },
  { id: 'flow', label: 'Flow' },
  { id: 'picker', label: 'Picker' },
  { id: 'whatif', label: 'What-If & Greeks' },
];

const SCENARIO_LABELS: { key: 'fast_target' | 'slow_target' | 'sideways' | 'adverse_stop' | 'iv_crush_target'; label: string }[] = [
  { key: 'fast_target', label: 'Fast target' },
  { key: 'slow_target', label: 'Slow target' },
  { key: 'sideways', label: 'Sideways' },
  { key: 'adverse_stop', label: 'Adverse stop' },
  { key: 'iv_crush_target', label: 'IV crush' },
];

const STRIKE_TYPE_LABELS: Record<string, string> = {
  DEEP_ITM: 'Deep ITM',
  ITM_1: 'ITM',
  ATM: 'ATM',
  OTM_1: 'OTM',
  DEEP_OTM: 'Deep OTM',
};

function errMsg(e: unknown, fallback: string): string {
  return e instanceof Error && e.message ? e.message : fallback;
}

/** Strike/expiry code the options-intelligence selector accepts. */
function toUnderlyingCode(instrument: string): 'NIFTY' | 'BANKNIFTY' | 'SENSEX' | null {
  const s = instrument.toUpperCase().replace(/[^A-Z]/g, '');
  if (s.includes('BANKNIFTY')) return 'BANKNIFTY';
  if (s.includes('SENSEX')) return 'SENSEX';
  if (s === 'NIFTY' || s === 'NIFTY50') return 'NIFTY';
  return null;
}

function unwrapEnvelope<T>(res: unknown): T {
  if (res !== null && typeof res === 'object' && 'data' in (res as Record<string, unknown>)) {
    return (res as { data: T }).data;
  }
  return res as T;
}

function asNum(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function asStr(v: unknown): string | null {
  return typeof v === 'string' && v.length > 0 ? v : null;
}

/** SCREAMING_SNAKE backend enum → sentence case for display. */
function humanize(v: unknown): string {
  if (typeof v !== 'string' || v.length === 0) return '—';
  return v.toLowerCase().replace(/_/g, ' ');
}

function toneForFlow(v: unknown): 'chip--up' | 'chip--down' | 'chip--neut' {
  const s = String(v ?? '').toUpperCase();
  if (s.includes('BULLISH') || s === 'BULL') return 'chip--up';
  if (s.includes('BEARISH') || s === 'BEAR') return 'chip--down';
  return 'chip--neut';
}

interface PickerCandidate {
  strike: number;
  strike_type: string;
  option_type: string;
  theoretical_price: number | null;
  market_premium: number | null;
  theta_drag_ratio: number | null;
  spread_friction_pct: number | null;
  net_rr_ratio: number | null;
  score: number | null;
  is_acceptable: boolean;
}

interface PickerSelection {
  underlying: string;
  direction: string;
  brokerSymbol: string | null;
  lotSize: number | null;
  selectedStrike: number | null;
  selectedStrikeType: string | null;
  selectionRationale: string[];
  selectionScore: number | null;
  isViable: boolean;
  nonViabilityReasons: string[];
  candidates: PickerCandidate[];
}

interface MoveBand {
  expectedMovePoints: number | null;
  conservativeMovePoints: number | null;
  aggressiveMovePoints: number | null;
  expectedMovePct: number | null;
  expectedDurationHours: number | null;
  fastEnough: boolean | null;
  velocityAssessment: string | null;
}

interface SimScenarioView {
  label: string;
  exit: number | null;
  netPnl: number | null;
  netReturnPct: number | null;
  friction: number | null;
  profitable: boolean | null;
}

interface AffordView {
  requiredMargin: number | null;
  availableMargin: number | null;
  premium: number | null;
  affordable: boolean | null;
}

function toPickerSelection(raw: unknown): PickerSelection | null {
  if (raw === null || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const contract = (r.selected_contract ?? {}) as Record<string, unknown>;
  const rawCandidates = Array.isArray(r.all_candidates) ? (r.all_candidates as unknown[]) : [];
  const candidates: PickerCandidate[] = rawCandidates
    .filter((c): c is Record<string, unknown> => c !== null && typeof c === 'object')
    .map((c) => ({
      strike: asNum(c.strike) ?? NaN,
      strike_type: asStr(c.strike_type) ?? '',
      option_type: asStr(c.option_type) ?? '',
      theoretical_price: asNum(c.theoretical_price),
      market_premium: asNum(c.market_premium),
      theta_drag_ratio: asNum(c.theta_drag_ratio),
      spread_friction_pct: asNum(c.spread_friction_pct),
      net_rr_ratio: asNum(c.net_rr_ratio),
      score: asNum(c.score),
      is_acceptable: c.is_acceptable === true,
    }))
    .filter((c) => Number.isFinite(c.strike));
  const strike = asNum(r.selected_strike);
  if (strike === null) return null;
  const rationale = Array.isArray(r.selection_rationale)
    ? (r.selection_rationale as unknown[]).filter((x): x is string => typeof x === 'string')
    : [];
  const nonViable = Array.isArray(r.non_viability_reasons)
    ? (r.non_viability_reasons as unknown[]).filter((x): x is string => typeof x === 'string')
    : [];
  return {
    underlying: asStr(r.underlying) ?? '',
    direction: asStr(r.direction) ?? '',
    brokerSymbol: asStr(contract.broker_symbol),
    lotSize: asNum(contract.lot_size),
    selectedStrike: strike,
    selectedStrikeType: asStr(r.selected_strike_type),
    selectionRationale: rationale,
    selectionScore: asNum(r.selection_score),
    isViable: r.is_viable === true,
    nonViabilityReasons: nonViable,
    candidates,
  };
}

function toMoveBand(raw: unknown): MoveBand | null {
  if (raw === null || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  if (asNum(r.expected_move_points) === null) return null;
  return {
    expectedMovePoints: asNum(r.expected_move_points),
    conservativeMovePoints: asNum(r.conservative_move_points),
    aggressiveMovePoints: asNum(r.aggressive_move_points),
    expectedMovePct: asNum(r.expected_move_pct),
    expectedDurationHours: asNum(r.expected_duration_hours),
    fastEnough: typeof r.is_fast_enough_for_option === 'boolean' ? r.is_fast_enough_for_option : null,
    velocityAssessment: asStr(r.velocity_assessment),
  };
}

function toSimScenarios(raw: unknown): SimScenarioView[] | null {
  if (raw === null || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const out: SimScenarioView[] = [];
  for (const { key, label } of SCENARIO_LABELS) {
    const s = r[key];
    if (s === null || typeof s !== 'object') return null;
    const sc = s as Record<string, unknown>;
    out.push({
      label,
      exit: asNum(sc.underlying_exit_price),
      netPnl: asNum(sc.net_pnl_total),
      netReturnPct: asNum(sc.net_return_pct),
      friction: asNum(sc.friction_total),
      profitable: typeof sc.is_profitable === 'boolean' ? sc.is_profitable : null,
    });
  }
  return out;
}

function toAffordView(raw: unknown): AffordView | null {
  if (raw === null || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  if (asNum(r.required_margin) === null && asNum(r.available_margin) === null) return null;
  return {
    requiredMargin: asNum(r.required_margin),
    availableMargin: asNum(r.available_margin),
    premium: asNum(r.premium),
    affordable: typeof r.affordable === 'boolean' ? r.affordable : null,
  };
}

export const OptionsChainDrawer = memo(function OptionsChainDrawer({
  isOpen,
  onClose,
  instrument,
  direction,
}: OptionsChainDrawerProps) {
  const [chain, setChain] = useState<OptionChainResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedExpiry, setSelectedExpiry] = useState<string>('');
  const [expiryNotice, setExpiryNotice] = useState<string | null>(null);
  const [tab, setTab] = useState<DrawerTab>('quotes');
  const [expandedStrikes, setExpandedStrikes] = useState<Record<number, boolean>>({});
  const requestIdRef = useRef(0);
  const panelRef = useRef<HTMLDivElement | null>(null);
  // Latest selected expiry for loadChain without re-creating it on each pick
  // (a loadChain identity change would re-trigger the open/load effect).
  const selectedExpiryRef = useRef(selectedExpiry);
  useEffect(() => {
    selectedExpiryRef.current = selectedExpiry;
  }, [selectedExpiry]);

  const [flow, setFlow] = useState<InstitutionalFlowResponse | null>(null);
  const [flowLoading, setFlowLoading] = useState(false);
  const [flowError, setFlowError] = useState<string | null>(null);
  const [maxPain, setMaxPain] = useState<MaxPainResult | null>(null);
  const flowReqRef = useRef(0);

  const [pickerDirection, setPickerDirection] = useState<DrawerDirection>(direction ?? 'NEUTRAL');
  const [pickerSpotText, setPickerSpotText] = useState('');
  const [pickerStopText, setPickerStopText] = useState('');
  const [pickerBusy, setPickerBusy] = useState(false);
  const [pickerError, setPickerError] = useState<string | null>(null);
  const [selection, setSelection] = useState<PickerSelection | null>(null);
  const [rankedExpiry, setRankedExpiry] = useState<string>('');
  const [moveBand, setMoveBand] = useState<MoveBand | null>(null);
  const [moveNote, setMoveNote] = useState<string | null>(null);
  const [scenarios, setScenarios] = useState<SimScenarioView[] | null>(null);
  const [simNote, setSimNote] = useState<string | null>(null);
  const [afford, setAfford] = useState<AffordView | null>(null);
  const [affordNote, setAffordNote] = useState<string | null>(null);

  // What-If tab state
  const [calcSpot, setCalcSpot] = useState<string>('');
  const [calcStrike, setCalcStrike] = useState<string>('');
  const [calcDte, setCalcDte] = useState<string>('5');
  const [calcIv, setCalcIv] = useState<string>('15');
  const [calcType, setCalcType] = useState<'CE' | 'PE'>('CE');
  const [calcGreeksResult, setCalcGreeksResult] = useState<any | null>(null);
  const [calcGreeksBusy, setCalcGreeksBusy] = useState<boolean>(false);
  const [calcGreeksError, setCalcGreeksError] = useState<string | null>(null);

  const [solvePrice, setSolvePrice] = useState<string>('');
  const [solveIvResult, setSolveIvResult] = useState<any | null>(null);
  const [solveIvBusy, setSolveIvBusy] = useState<boolean>(false);
  const [solveIvError, setSolveIvError] = useState<string | null>(null);

  const [portfolioGreeks, setPortfolioGreeks] = useState<any | null>(null);
  const [portfolioGreeksLoading, setPortfolioGreeksLoading] = useState<boolean>(false);
  const [portfolioGreeksError, setPortfolioGreeksError] = useState<string | null>(null);

  // Verdict-driven default side; the coordinator passes the bias direction.
  useEffect(() => {
    if (direction) setPickerDirection(direction);
  }, [direction]);

  const loadChain = useCallback(
    async (expiryOverride?: string) => {
      if (!instrument) return;
      const requestId = ++requestIdRef.current;
      const requestedExpiry = expiryOverride ?? selectedExpiryRef.current;
      // '' must become undefined so api omits ?expiry= (api encodes when present)
      const expiryParam = expiryOverride ? expiryOverride : undefined;
      setLoading(true);
      setError(null);
      try {
        const res = await api.getOptionChain(instrument, expiryParam);
        // Guard race: ignore late response from old instrument/expiry
        if (requestIdRef.current !== requestId) return;
        if (!res?.data) {
          setError('Options chain response was empty.');
          return;
        }
        setChain(res.data);
        // Reconcile a server-substituted expiry into the selector on every
        // load so the picker and the rendered table can never diverge; the
        // substitution is stated visibly rather than silently absorbed.
        const serverExpiry = typeof res.data.expiry === 'string' && res.data.expiry ? res.data.expiry : '';
        if (serverExpiry) {
          setSelectedExpiry(serverExpiry);
          selectedExpiryRef.current = serverExpiry;
          setExpiryNotice(
            requestedExpiry && requestedExpiry !== serverExpiry
              ? `Expiry ${requestedExpiry} unavailable — backend returned ${serverExpiry}.`
              : null,
          );
        } else {
          setExpiryNotice(requestedExpiry ? `Expiry ${requestedExpiry} unavailable — backend returned no expiry.` : null);
        }
      } catch (e) {
        if (requestIdRef.current === requestId) {
          setError(e instanceof Error ? e.message : 'Failed to load options chain');
        }
      } finally {
        if (requestIdRef.current === requestId) setLoading(false);
      }
    },
    [instrument],
  );

  const loadFlow = useCallback(async () => {
    if (!instrument) return;
    const requestId = ++flowReqRef.current;
    const expiryParam = selectedExpiry || chain?.expiry || undefined;
    setFlowLoading(true);
    setFlowError(null);
    try {
      const res = await api.getInstitutionalFlow(instrument, expiryParam);
      if (flowReqRef.current !== requestId) return;
      if (res?.error) {
        setFlow(null);
        setFlowError(res.error);
      } else {
        setFlow(res?.data ?? null);
      }
    } catch (e) {
      if (flowReqRef.current === requestId) {
        setFlow(null);
        setFlowError(errMsg(e, 'Failed to load institutional flow'));
      }
    } finally {
      if (flowReqRef.current === requestId) setFlowLoading(false);
    }
    // Payout curve is context only; its failure never blocks the flow view.
    try {
      const mp = await api.getMaxPain(instrument, expiryParam);
      if (flowReqRef.current === requestId) setMaxPain(mp?.data ?? null);
    } catch {
      if (flowReqRef.current === requestId) setMaxPain(null);
    }
  }, [instrument, selectedExpiry, chain]);

  const runPicker = useCallback(async () => {
    const chainSpot = chain?.spot_price ?? chain?.analytics?.spot_price ?? NaN;
    const spot = pickerSpotText.trim() === '' ? chainSpot : Number(pickerSpotText);
    const stop = Number(pickerStopText);
    if (!Number.isFinite(spot) || spot <= 0) {
      setPickerError('Enter a spot price above zero to rank a contract.');
      return;
    }
    if (!Number.isFinite(stop) || stop <= 0) {
      setPickerError('Enter a stop level above zero to rank a contract.');
      return;
    }
    if (stop === spot) {
      setPickerError('Stop matches spot — move it away from spot so risk has a size.');
      return;
    }
    const code = toUnderlyingCode(instrument);
    if (!code) {
      setPickerError(
        `Contract selection is unavailable for ${instrument}: the selector covers NIFTY, BANKNIFTY and SENSEX only.`,
      );
      return;
    }
    if (pickerDirection === 'NEUTRAL') {
      setPickerError('No directional side selected — choose Bullish or Bearish to rank a contract.');
      return;
    }
    const analytics = chain?.analytics;
    // Backend publishes chain analytics.atm_iv in PERCENT (options_service
    // rounds solved IV ×100); the intelligence endpoints take a fraction.
    // No live IV = no ranking — never a hardcoded 0.16 baseline.
    const atmIvPct = asNum(analytics?.atm_iv);
    if (atmIvPct === null || atmIvPct <= 0) {
      setPickerError('ATM IV unavailable — cannot rank a contract without a live volatility input.');
      return;
    }
    const iv = atmIvPct / 100;
    const dteRaw = asNum(analytics?.time_to_expiry_days);
    const dte = dteRaw !== null && dteRaw > 0 ? dteRaw : null;
    const longDir = pickerDirection === 'BULLISH' ? 'LONG_CALL' : 'LONG_PUT';
    const optType = pickerDirection === 'BULLISH' ? 'CE' : 'PE';
    const stopPts = Math.abs(spot - stop);
    const expiryUsed = selectedExpiry || chain?.expiry || '';

    setPickerBusy(true);
    setPickerError(null);
    setSelection(null);
    setMoveBand(null);
    setMoveNote(null);
    setScenarios(null);
    setSimNote(null);
    setAfford(null);
    setAffordNote(null);
    try {
      // Expected move first: the selector ranks against its magnitude.
      let movePts: number | null = null;
      try {
        const emRaw = await api.projectExpectedMove({
          underlying: code,
          spot,
          direction: pickerDirection,
          horizon: 'INTRADAY',
          current_iv: iv,
        });
        const band = toMoveBand(unwrapEnvelope<unknown>(emRaw));
        if (band) {
          setMoveBand(band);
          movePts = band.expectedMovePoints;
        } else {
          setMoveNote('Expected move came back empty — target falls back to stop distance.');
        }
      } catch (e) {
        setMoveNote(`Expected move unavailable — ${errMsg(e, 'backend refused the request')}. Target falls back to stop distance.`);
      }

      // Fail-closed: a 400 here means no live chain quotes — surface the
      // backend reason verbatim, never a modelled guess.
      const selRaw = await api.selectOptimalContract({
        underlying: code,
        spot_price: spot,
        direction: longDir,
        expected_move_points: movePts ?? undefined,
        stop_loss_points: stopPts,
        target_horizon_hours: 1,
        current_iv: iv,
      });
      const sel = toPickerSelection(unwrapEnvelope<unknown>(selRaw));
      if (!sel) {
        setPickerError('Contract selection came back empty — no ranked contract to show.');
        return;
      }
      setSelection(sel);
      setRankedExpiry(expiryUsed);

      const targetPts = movePts ?? stopPts;
      const targetSpot = pickerDirection === 'BULLISH' ? spot + targetPts : spot - targetPts;
      // No lot size published = no simulated position, never a fabricated 75.
      const lot = sel.lotSize !== null && sel.lotSize > 0 ? Math.min(Math.round(sel.lotSize), 500) : null;
      if (dte === null) {
        setSimNote('Path simulation unavailable — days-to-expiry not published for this chain.');
      } else if (lot === null) {
        setSimNote('Path simulation unavailable — contract lot size not published.');
      } else {
        try {
          const simRaw = await api.simulateOptionPath({
            underlying: code,
            spot,
            strike: sel.selectedStrike,
            option_type: optType,
            dte_days: dte,
            iv,
            target_spot: targetSpot,
            stop_spot: stop,
            quantity: lot,
          });
          const sims = toSimScenarios(unwrapEnvelope<unknown>(simRaw));
          if (sims) {
            setScenarios(sims);
          } else {
            setSimNote('Path simulation came back empty — no scenario table to show.');
          }
        } catch (e) {
          setSimNote(`Path simulation unavailable — ${errMsg(e, 'backend refused the request')}.`);
        }
      }

      // Affordability is advisory only, and only when the client offers it.
      const maybePreview = api as unknown as {
        previewPaperMargin?: (p: {
          symbol: string;
          underlying: string;
          side: 'BUY' | 'SELL';
          quantity: number;
          price: number;
        }) => Promise<unknown>;
      };
      const premium = sel.candidates.find((c) => c.strike === sel.selectedStrike)?.market_premium
        ?? sel.candidates.find((c) => c.strike === sel.selectedStrike)?.theoretical_price
        ?? null;
      if (typeof maybePreview.previewPaperMargin === 'function' && sel.brokerSymbol && premium !== null && premium > 0 && lot !== null) {
        try {
          const affRaw = await maybePreview.previewPaperMargin({
            symbol: sel.brokerSymbol,
            underlying: code,
            side: 'BUY',
            quantity: lot,
            price: premium,
          });
          setAfford(toAffordView(unwrapEnvelope<unknown>(affRaw)));
        } catch (e) {
          setAfford(null);
          setAffordNote(`paper margin preview unavailable — ${errMsg(e, 'backend refused the request')}`);
        }
      } else if (sel.brokerSymbol && (lot === null || premium === null || premium <= 0)) {
        setAffordNote('paper margin preview unavailable — contract size or premium not published');
      }
    } catch (e) {
      setPickerError(errMsg(e, 'Contract selection failed.'));
      setSelection(null);
    } finally {
      setPickerBusy(false);
    }
  }, [chain, pickerSpotText, pickerStopText, pickerDirection, instrument, selectedExpiry]);


  // Reset stale expiry when instrument changes; don't reuse old instrument's expiry.
  useEffect(() => {
    setSelectedExpiry('');
    selectedExpiryRef.current = '';
    setExpiryNotice(null);
  }, [instrument]);

  // Open / instrument change: clear stale chain and load default expiry (single fetch).
  useEffect(() => {
    if (!isOpen || !instrument) return;
    setChain(null);
    void loadChain();
  }, [isOpen, instrument, loadChain]);

  // Flow tab lazily loads walls/sentiment/build-ups for the active expiry.
  useEffect(() => {
    if (!isOpen || tab !== 'flow' || !instrument) return;
    void loadFlow();
  }, [isOpen, tab, instrument, loadFlow]);

  // What-If tab loads portfolio greeks summary and populates spot/strike defaults
  const loadPortfolioGreeks = useCallback(async () => {
    setPortfolioGreeksLoading(true);
    setPortfolioGreeksError(null);
    try {
      const res = await api.getPortfolioGreeksSummary();
      setPortfolioGreeks(res?.data ?? res);
    } catch (e) {
      setPortfolioGreeks(null);
      setPortfolioGreeksError(errMsg(e, 'portfolio Greeks unavailable'));
    } finally {
      setPortfolioGreeksLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isOpen || tab !== 'whatif') return;
    void loadPortfolioGreeks();
  }, [isOpen, tab, loadPortfolioGreeks]);

  useEffect(() => {
    if (chain?.spot_price && !calcSpot) {
      setCalcSpot(String(chain.spot_price));
      const atm = chain.analytics?.atm_strike ?? Math.round(chain.spot_price / 50) * 50;
      setCalcStrike(String(atm));
    }
  }, [chain, calcSpot]);

  const handleCalculateGreeks = useCallback(async () => {
    const spot = parseFloat(calcSpot);
    const strike = parseFloat(calcStrike);
    const dte = parseFloat(calcDte);
    const iv = parseFloat(calcIv) / 100;
    if (!spot || !strike || !dte || !iv) {
      setCalcGreeksError('Enter spot, strike, DTE and IV above zero.');
      return;
    }
    setCalcGreeksBusy(true);
    setCalcGreeksError(null);
    try {
      const res = await api.calculateGreeks({
        spot,
        strike,
        dte_days: dte,
        volatility: iv,
        option_type: calcType,
      });
      setCalcGreeksResult(res?.data ?? res);
    } catch (err) {
      setCalcGreeksError(errMsg(err, 'Failed to calculate Greeks'));
    } finally {
      setCalcGreeksBusy(false);
    }
  }, [calcSpot, calcStrike, calcDte, calcIv, calcType]);

  const handleSolveIV = useCallback(async () => {
    const spot = parseFloat(calcSpot);
    const strike = parseFloat(calcStrike);
    const dte = parseFloat(calcDte);
    const price = parseFloat(solvePrice);
    if (!spot || !strike || !dte || !price) {
      setSolveIvError('Enter a market premium plus spot, strike and DTE above zero.');
      return;
    }
    setSolveIvBusy(true);
    setSolveIvError(null);
    try {
      const res = await api.solveIV({
        market_price: price,
        spot,
        strike,
        dte_days: dte,
        option_type: calcType,
      });
      setSolveIvResult(res?.data ?? res);
    } catch (err) {
      setSolveIvError(errMsg(err, 'Failed to solve IV'));
    } finally {
      setSolveIvBusy(false);
    }
  }, [calcSpot, calcStrike, calcDte, solvePrice, calcType]);

  // Handle ESC key to close
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Dialog focus: land inside the panel on open, then keep Tab cycling within
  // it so focus can never wander back to the desk controls behind the scrim.
  useEffect(() => {
    if (!isOpen) return;
    panelRef.current?.focus();
  }, [isOpen]);

  const onPanelKeyDown = useCallback((e: ReactKeyboardEvent) => {
    if (e.key !== 'Tab') return;
    const root = panelRef.current;
    if (!root) return;
    const focusables = root.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), select:not([disabled]), input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    if (focusables.length === 0) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }, []);

  const handleRefresh = useCallback(() => {
    void loadChain(selectedExpiry);
    if (tab === 'flow') void loadFlow();
    if (tab === 'whatif') void loadPortfolioGreeks();
  }, [loadChain, loadFlow, loadPortfolioGreeks, selectedExpiry, tab]);

  const toggleStrike = useCallback((strike: number) => {
    setExpandedStrikes((prev) => ({ ...prev, [strike]: !prev[strike] }));
  }, []);

  const onTabKeyDown = useCallback(
    (e: ReactKeyboardEvent) => {
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
      e.preventDefault();
      const order: DrawerTab[] = TABS.map((t) => t.id);
      const idx = order.indexOf(tab);
      const next = e.key === 'ArrowRight'
        ? order[(idx + 1) % order.length]
        : order[(idx + order.length - 1) % order.length];
      setTab(next);
      document.getElementById(`oc-tab-${next}`)?.focus();
    },
    [tab],
  );

  if (!isOpen) return null;

  const analytics = chain?.analytics;
  const strikes: OptionChainStrikeRow[] = chain?.strikes ?? [];
  const spotPrice = chain?.spot_price ?? analytics?.spot_price ?? 0;

  // Filter ~15 strikes centered around ATM for instant glance without lag
  const atmIndex = strikes.findIndex((s) => s.is_atm);
  const startIndex = atmIndex >= 0 ? Math.max(0, atmIndex - 8) : 0;
  const visibleStrikes = strikes.slice(startIndex, startIndex + 17);

  const flowFlows = flow?.strike_flows ?? [];
  const flowAtm = flowFlows.findIndex((s) => s.is_atm);
  const flowStart = flowAtm >= 0 ? Math.max(0, flowAtm - 8) : 0;
  const visibleFlows = flowFlows.slice(flowStart, flowStart + 17);
  const flowHasContent =
    visibleFlows.length > 0 ||
    asNum(flow?.call_wall_strike) !== null ||
    asNum(flow?.put_floor_strike) !== null;

  const rankedCandidates = selection
    ? [...selection.candidates].sort((a, b) => (b.score ?? -1) - (a.score ?? -1)).slice(0, 5)
    : [];

  // z-[60] sits above the AI copilot panel (z-50) instead of tying with it.
  return (
    <div className="fixed inset-0 z-[60] flex justify-end bg-foreground/40 backdrop-blur-2xs transition-opacity animate-in fade-in">
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={`Option chain · ${instrument}`}
        tabIndex={-1}
        onKeyDown={onPanelKeyDown}
        className="w-full max-w-4xl h-full bg-card border-l border-border-strong flex flex-col overflow-hidden outline-none"
        style={{ boxShadow: 'var(--ds-shadow-lg)' }}
      >
        {/* Header */}
        <div className="p-3.5 border-b border-border flex items-center justify-between gap-3 bg-surface-subtle">
          <div className="flex items-center gap-2.5">
            <h2 className="text-[13px] font-semibold tracking-normal text-foreground">Option chain</h2>
            <span className="chip chip--info num">
              {instrument}
            </span>
          </div>

          <div className="flex items-center gap-2">
            {/* Expiry selector */}
            {chain?.expiries && chain.expiries.length > 0 && (
              <select
                aria-label="Select Expiry"
                value={selectedExpiry}
                onChange={(e) => {
                  const next = e.target.value;
                  setSelectedExpiry(next);
                  void loadChain(next);
                  // Flow tab refetches via its effect once selectedExpiry settles.
                }}
                className="text-xs font-mono py-1 px-2.5 rounded border border-border-strong bg-card text-foreground font-semibold cursor-pointer shadow-2xs"
              >
                {chain.expiries.map((exp) => (
                  <option key={exp} value={exp}>
                    {exp}
                  </option>
                ))}
              </select>
            )}

            <button
              type="button"
              onClick={handleRefresh}
              disabled={loading}
              title="Refresh Options Chain"
              className="p-1.5 rounded border border-border-strong bg-card hover:bg-surface-subtle text-muted-foreground shadow-2xs cursor-pointer"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>

            <button
              type="button"
              onClick={onClose}
              title="Close (Esc)"
              className="p-1.5 rounded border border-border-strong bg-card hover:bg-surface-subtle text-muted-foreground shadow-2xs cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {expiryNotice ? (
          <div role="status" className="notice notice--warn" style={{ margin: '8px 12px 0', fontSize: 11.5 }}>
            {expiryNotice}
          </div>
        ) : null}

        {/* Key Metrics Strip */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5 p-3.5 border-b border-border bg-surface-subtle/60 font-mono text-xs">
          <div className="p-2.5 rounded-md bg-card border border-border">
            <span className="micro-label block">Spot price</span>
            <span className="font-semibold text-sm text-foreground num">{spotPrice ? fmtNum(spotPrice, 1) : '—'}</span>
          </div>
          <div className="p-2.5 rounded-md bg-card border border-border">
            <span className="micro-label block">Max pain strike</span>
            <span className="font-semibold text-sm text-accent-strong num">
              {analytics?.max_pain_strike ? Math.round(analytics.max_pain_strike) : '—'}
            </span>
          </div>
          <div className="p-2.5 rounded-md bg-card border border-border">
            <span className="micro-label block">PCR (OI)</span>
            <span
              className={`font-semibold text-sm num ${
                typeof analytics?.pcr_oi === 'number' && Number.isFinite(analytics.pcr_oi)
                  ? analytics.pcr_oi >= 1
                    ? 'text-up-strong'
                    : 'text-down-strong'
                  : ''
              }`}
            >
              {typeof analytics?.pcr_oi === 'number' && Number.isFinite(analytics.pcr_oi) ? fmtNum(analytics.pcr_oi, 2) : '—'}
            </span>
          </div>
          <div className="p-2.5 rounded-md bg-card border border-border">
            <span className="micro-label block">ATM implied vol (IV)</span>
            {/* Backend already publishes solved IV in percent — no ×100 here. */}
            <span className="font-semibold text-sm text-foreground num">
              {typeof analytics?.atm_iv === 'number' && Number.isFinite(analytics.atm_iv) ? `${fmtNum(analytics.atm_iv, 1)}%` : '—'}
            </span>
          </div>
          <div className="p-2.5 rounded-md bg-card border border-border">
            <span className="micro-label block">Total CE / PE OI</span>
            <span className="font-semibold text-xs text-foreground num">
              {analytics?.total_call_oi ? `${Math.round(analytics.total_call_oi / 100000)}L / ` : ''}
              {analytics?.total_put_oi ? `${Math.round(analytics.total_put_oi / 100000)}L` : '—'}
            </span>
          </div>
          <div className="p-2.5 rounded-md bg-card border border-border">
            <span className="micro-label block">PCR (Vol)</span>
            <span
              className={`font-semibold text-sm num ${
                typeof analytics?.pcr_volume === 'number' && Number.isFinite(analytics.pcr_volume)
                  ? analytics.pcr_volume >= 1
                    ? 'text-up-strong'
                    : 'text-down-strong'
                  : ''
              }`}
            >
              {typeof analytics?.pcr_volume === 'number' && Number.isFinite(analytics.pcr_volume) ? fmtNum(analytics.pcr_volume, 2) : '—'}
            </span>
          </div>
          <div className="p-2.5 rounded-md bg-card border border-border">
            <span className="micro-label block">Total CE / PE vol</span>
            <span className="font-semibold text-xs text-foreground num">
              {analytics?.total_call_volume ? `${Math.round(analytics.total_call_volume / 100000)}L / ` : ''}
              {analytics?.total_put_volume ? `${Math.round(analytics.total_put_volume / 100000)}L` : '—'}
            </span>
          </div>
          <div className="p-2.5 rounded-md bg-card border border-border">
            <span className="micro-label block">IV skew (put − call)</span>
            <span className="font-semibold text-sm text-foreground num">
              {analytics?.iv_skew === null || analytics?.iv_skew === undefined ? '—' : fmtNum(analytics.iv_skew, 2)}
            </span>
          </div>
          <div className="p-2.5 rounded-md bg-card border border-border">
            <span className="micro-label block">ATM strike</span>
            <span className="font-semibold text-sm text-foreground num">
              {analytics?.atm_strike ? Math.round(analytics.atm_strike) : '—'}
            </span>
          </div>
          <div className="p-2.5 rounded-md bg-card border border-border">
            <span className="micro-label block">Days to expiry</span>
            <span className="font-semibold text-sm text-foreground num">
              {typeof analytics?.time_to_expiry_days === 'number' && Number.isFinite(analytics.time_to_expiry_days)
                ? `${fmtNum(analytics.time_to_expiry_days, 0)}d`
                : '—'}
            </span>
          </div>
        </div>

        {/* View tabs */}
        <div className="px-3.5 pt-2.5 bg-surface-subtle/60 border-b border-border">
          <div role="tablist" aria-label="Options chain views" className="tabbar" onKeyDown={onTabKeyDown}>
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                id={`oc-tab-${t.id}`}
                aria-selected={tab === t.id}
                aria-controls={`oc-panel-${t.id}`}
                tabIndex={tab === t.id ? 0 : -1}
                className={`tab ${tab === t.id ? 'is-active' : ''}`}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* Table Matrix */}
        <div className="flex-1 overflow-y-auto p-2">
          {tab === 'quotes' ? (
            <div role="tabpanel" id="oc-panel-quotes" aria-labelledby="oc-tab-quotes">
              {error ? (
                <div
                  role="alert"
                  className="p-3 mb-2 rounded-md border border-down-line bg-down-wash flex items-center justify-between gap-3 text-xs"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-down-strong">Error loading option chain:</span>
                    <span className="text-down">{error}</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => void loadChain(selectedExpiry)}
                    className="px-2.5 py-1 rounded bg-card border border-down-line font-semibold text-down-strong hover:bg-down-wash cursor-pointer"
                  >
                    Retry
                  </button>
                </div>
              ) : null}

              {loading && !chain ? (
                <div className="space-y-2 p-2" aria-label="Loading options chain">
                  {Array.from({ length: 8 }).map((_, i) => (
                    <div key={i} className="h-8 rounded bg-muted animate-pulse" />
                  ))}
                </div>
              ) : strikes.length === 0 ? (

                <div className="flex h-full items-center justify-center p-8 text-center text-sm text-ink-3">
                  No options data available for {instrument}
                  {selectedExpiry ? ` (${selectedExpiry})` : ''}. Try another expiry or refresh.
                </div>
              ) : (
              <table className="w-full text-xs font-mono border-collapse">
                <thead className="sticky top-0 bg-card z-10 text-[11px]">
                  <tr className="border-b border-border">
                    <th colSpan={4} className="py-1.5 px-2 text-center text-up-strong bg-up-wash font-semibold uppercase border-r border-border">
                      Calls · CE
                    </th>
                    <th className="py-1.5 px-3 text-center text-foreground bg-muted font-semibold uppercase border-r border-border">
                      Strike
                    </th>
                    <th colSpan={4} className="py-1.5 px-2 text-center text-down-strong bg-down-wash font-semibold uppercase">
                      Puts · PE
                    </th>
                  </tr>
                  <tr className="border-b border-border text-[10px] text-ink-3 uppercase bg-surface-subtle">
                    <th className="py-1 px-2 text-right">OI</th>
                    <th className="py-1 px-2 text-right">Chg OI</th>
                    <th className="py-1 px-2 text-right">IV%</th>
                    <th className="py-1 px-2 text-right border-r border-border">LTP</th>
                    <th className="py-1 px-3 text-center text-foreground border-r border-border">ATM</th>
                    <th className="py-1 px-2 text-left">LTP</th>
                    <th className="py-1 px-2 text-left">IV%</th>
                    <th className="py-1 px-2 text-left">Chg OI</th>
                    <th className="py-1 px-2 text-left">OI</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleStrikes.map((row) => {
                    const call = row.call;
                    const put = row.put;
                    const isAtm = row.is_atm;
                    const open = expandedStrikes[row.strike] === true;

                    return (
                      <Fragment key={row.strike}>
                        <tr
                          className={`border-b border-muted hover:bg-surface-subtle transition-colors ${
                            isAtm ? 'bg-warn-wash' : ''
                          }`}
                        >
                          {/* CE Side */}
                          <td className="py-1.5 px-2 text-right text-ink-3">
                            {call?.open_interest ? `${Math.round(call.open_interest / 1000)}k` : '—'}
                          </td>
                          <td
                            className={`py-1.5 px-2 text-right num ${
                              (call?.oi_change ?? 0) >= 0 ? 'text-up-strong' : 'text-down-strong'
                            }`}
                          >
                            {call?.oi_change ? `${(call.oi_change > 0 ? '+' : '')}${Math.round(call.oi_change / 1000)}k` : '—'}
                          </td>
                          <td className="py-1.5 px-2 text-right text-ink-3">
                            {typeof call?.greeks?.iv === 'number' ? `${fmtNum(call.greeks.iv, 1)}%` : '—'}
                          </td>
                          <td className="py-1.5 px-2 text-right font-medium text-foreground num border-r border-border">
                            {call?.ltp ? fmtNum(call.ltp, 1) : '—'}
                          </td>

                          {/* Strike */}
                          <td
                            className={`py-1.5 px-3 text-center num border-r border-border ${
                              isAtm
                                ? 'text-warn-ink bg-warn-line font-semibold'
                                : 'text-foreground bg-surface-subtle'
                            }`}
                          >
                            <button
                              type="button"
                              onClick={() => toggleStrike(row.strike)}
                              aria-expanded={open}
                              aria-controls={`oc-greeks-${Math.round(row.strike)}`}
                              aria-label={`Greeks for ${Math.round(row.strike)} strike`}
                              title="Toggle Greeks"
                              className="inline-flex items-center gap-1 cursor-pointer bg-transparent border-0 font-inherit text-inherit"
                            >
                              <span>{Math.round(row.strike)}</span>
                              <ChevronDown className={`w-3 h-3 text-ink-3 transition-transform ${open ? 'rotate-180' : ''}`} />
                            </button>
                          </td>

                          {/* PE Side */}
                          <td className="py-1.5 px-2 text-left font-medium text-foreground num">
                            {put?.ltp ? fmtNum(put.ltp, 1) : '—'}
                          </td>
                          <td className="py-1.5 px-2 text-left text-ink-3">
                            {typeof put?.greeks?.iv === 'number' ? `${fmtNum(put.greeks.iv, 1)}%` : '—'}
                          </td>
                          <td
                            className={`py-1.5 px-2 text-left num ${
                              (put?.oi_change ?? 0) >= 0 ? 'text-up-strong' : 'text-down-strong'
                            }`}
                          >
                            {put?.oi_change ? `${(put.oi_change > 0 ? '+' : '')}${Math.round(put.oi_change / 1000)}k` : '—'}
                          </td>
                          <td className="py-1.5 px-2 text-left text-ink-3">
                            {put?.open_interest ? `${Math.round(put.open_interest / 1000)}k` : '—'}
                          </td>
                        </tr>
                        {open ? (
                          <tr key={`${row.strike}-greeks`} id={`oc-greeks-${Math.round(row.strike)}`} className="border-b border-muted bg-surface-subtle/60">
                            <td colSpan={9} className="py-2 px-3">
                              <div className="grid grid-cols-2 gap-3 text-[11px]">
                                <div>
                                  <span className="micro-label block">Call Greeks · {Math.round(row.strike)} CE</span>
                                  <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 num text-ink-3">
                                    <span>Delta {call?.greeks ? fmtNum(call.greeks.delta, 3) : '—'}</span>
                                    <span>Theta {call?.greeks ? fmtNum(call.greeks.theta, 2) : '—'}</span>
                                    <span>Vega {call?.greeks ? fmtNum(call.greeks.vega, 2) : '—'}</span>
                                  </div>
                                </div>
                                <div>
                                  <span className="micro-label block">Put Greeks · {Math.round(row.strike)} PE</span>
                                  <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 num text-ink-3">
                                    <span>Delta {put?.greeks ? fmtNum(put.greeks.delta, 3) : '—'}</span>
                                    <span>Theta {put?.greeks ? fmtNum(put.greeks.theta, 2) : '—'}</span>
                                    <span>Vega {put?.greeks ? fmtNum(put.greeks.vega, 2) : '—'}</span>
                                  </div>
                                </div>
                              </div>
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
              )}
            </div>
          ) : null}

          {tab === 'flow' ? (
            <div role="tabpanel" id="oc-panel-flow" aria-labelledby="oc-tab-flow" className="p-1.5 space-y-3">
              {flowError ? (
                <div
                  role="alert"
                  className="p-3 rounded-md border border-down-line bg-down-wash flex items-center justify-between gap-3 text-xs"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-down-strong">Error loading institutional flow:</span>
                    <span className="text-down">{flowError}</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => void loadFlow()}
                    className="px-2.5 py-1 rounded bg-card border border-down-line font-semibold text-down-strong hover:bg-down-wash cursor-pointer"
                  >
                    Retry
                  </button>
                </div>
              ) : null}

              {flowLoading && !flow ? (
                <div className="space-y-2 p-2" aria-label="Loading institutional flow">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <div key={i} className="h-8 rounded bg-muted animate-pulse" />
                  ))}
                </div>
              ) : !flowHasContent && !flowLoading ? (
                <div className="flex h-full items-center justify-center p-8 text-center text-sm text-ink-3">
                  No institutional flow published for this expiry
                  {selectedExpiry || chain?.expiry ? ` (${selectedExpiry || chain?.expiry})` : ''}.
                </div>
              ) : flow ? (
                <>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 font-mono text-xs">
                    <div className="p-2.5 rounded-md bg-card border border-border">
                      <span className="micro-label block">Sentiment</span>
                      <span className={`chip ${toneForFlow(flow.institutional_sentiment)} num`}>
                        {humanize(flow.institutional_sentiment)}
                      </span>
                      <span className="block mt-1 text-[11px] text-ink-3 num">
                        Score {fmtNum(flow.institutional_score, 0)}
                      </span>
                    </div>
                    <div className="p-2.5 rounded-md bg-card border border-border">
                      <span className="micro-label block">Call wall</span>
                      <span className="font-semibold text-sm text-foreground num">
                        {flow.call_wall_strike ? Math.round(flow.call_wall_strike) : '—'}
                      </span>
                    </div>
                    <div className="p-2.5 rounded-md bg-card border border-border">
                      <span className="micro-label block">Put floor</span>
                      <span className="font-semibold text-sm text-foreground num">
                        {flow.put_floor_strike ? Math.round(flow.put_floor_strike) : '—'}
                      </span>
                    </div>
                    <div className="p-2.5 rounded-md bg-card border border-border">
                      <span className="micro-label block">Max pain</span>
                      <span className="font-semibold text-sm text-accent-strong num">
                        {flow.max_pain_strike ? Math.round(flow.max_pain_strike) : '—'}
                      </span>
                    </div>
                  </div>

                  {visibleFlows.length > 0 ? (
                    <div className="tbl-wrap">
                      <table className="tbl num">
                        <thead>
                          <tr>
                            <th className="c">Strike</th>
                            <th>Call build-up</th>
                            <th>Put build-up</th>
                            <th>Net flow</th>
                            <th className="r">CE chg OI</th>
                            <th className="r">PE chg OI</th>
                          </tr>
                        </thead>
                        <tbody>
                          {visibleFlows.map((s) => (
                            <tr key={s.strike} className={s.is_atm ? 'bg-warn-wash' : undefined}>
                              <td className="c">{Math.round(s.strike)}</td>
                              <td>{humanize(s.call_buildup)}</td>
                              <td>{humanize(s.put_buildup)}</td>
                              <td>
                                <span className={`chip ${toneForFlow(s.net_flow)}`}>{humanize(s.net_flow)}</span>
                              </td>
                              <td className="r">
                                {s.call_oi_change
                                  ? `${s.call_oi_change > 0 ? '+' : ''}${Math.round(s.call_oi_change / 1000)}k`
                                  : '—'}
                              </td>
                              <td className="r">
                                {s.put_oi_change
                                  ? `${s.put_oi_change > 0 ? '+' : ''}${Math.round(s.put_oi_change / 1000)}k`
                                  : '—'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}

                  {maxPain && maxPain.strikes.length > 0 ? (
                    <details className="rounded-md border border-border bg-card p-2.5 text-xs">
                      <summary className="cursor-pointer font-semibold text-foreground">
                        Payout curve · max pain {Math.round(maxPain.max_pain_strike)}
                      </summary>
                      <div className="tbl-wrap mt-2">
                        <table className="tbl num">
                          <thead>
                            <tr>
                              <th className="r">Strike</th>
                              <th className="r">Total payout</th>
                            </tr>
                          </thead>
                          <tbody>
                            {maxPain.strikes.map((strike, i) => (
                              <tr
                                key={strike}
                                className={strike === maxPain.max_pain_strike ? 'bg-warn-wash' : undefined}
                              >
                                <td className="r">{Math.round(strike)}</td>
                                <td className="r">{fmtNum(maxPain.payouts[i], 0)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </details>
                  ) : null}
                </>
              ) : null}
            </div>
          ) : null}

          {tab === 'picker' ? (
            <div role="tabpanel" id="oc-panel-picker" aria-labelledby="oc-tab-picker" className="p-1.5 space-y-3">
              <form
                className="rounded-md border border-border bg-card p-3 grid grid-cols-2 sm:grid-cols-4 gap-2.5 items-end"
                onSubmit={(e) => {
                  e.preventDefault();
                  void runPicker();
                }}
              >
                <label className="field">
                  <span className="field-l micro-label">Direction</span>
                  <select
                    aria-label="Trade direction"
                    className="input"
                    value={pickerDirection}
                    onChange={(e) => setPickerDirection(e.target.value as DrawerDirection)}
                  >
                    <option value="BULLISH">Bullish</option>
                    <option value="BEARISH">Bearish</option>
                    <option value="NEUTRAL">Neutral</option>
                  </select>
                </label>
                <label className="field">
                  <span className="field-l micro-label">Spot</span>
                  <input
                    aria-label="Spot price"
                    className="input num"
                    inputMode="decimal"
                    placeholder={spotPrice ? fmtNum(spotPrice, 1) : 'Spot'}
                    value={pickerSpotText}
                    onChange={(e) => setPickerSpotText(e.target.value)}
                  />
                </label>
                <label className="field">
                  <span className="field-l micro-label">Stop level</span>
                  <input
                    aria-label="Stop level"
                    className="input num"
                    inputMode="decimal"
                    placeholder="Stop"
                    value={pickerStopText}
                    onChange={(e) => setPickerStopText(e.target.value)}
                  />
                </label>
                <button type="submit" disabled={pickerBusy} className="btn">
                  {pickerBusy ? 'Ranking…' : 'Rank contract'}
                </button>
              </form>

              {pickerError ? (
                <div
                  role="alert"
                  className="p-3 rounded-md border border-down-line bg-down-wash text-xs flex items-center justify-between gap-3"
                >
                  <span className="text-down">{pickerError}</span>
                  <button
                    type="button"
                    onClick={() => void runPicker()}
                    className="px-2.5 py-1 rounded bg-card border border-down-line font-semibold text-down-strong hover:bg-down-wash cursor-pointer shrink-0"
                  >
                    Retry
                  </button>
                </div>
              ) : null}

              {selection ? (
                <div className="rounded-md border border-border bg-card p-3 space-y-2.5 text-xs">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="chip chip--info num">
                      {selection.brokerSymbol ?? `${Math.round(selection.selectedStrike ?? 0)} ${pickerDirection === 'BULLISH' ? 'CE' : 'PE'}`}
                    </span>
                    {selection.selectedStrikeType ? (
                      <span className="chip chip--neut">{STRIKE_TYPE_LABELS[selection.selectedStrikeType] ?? selection.selectedStrikeType}</span>
                    ) : null}
                    <span className={`chip ${selection.isViable ? 'chip--up' : 'chip--warn'}`}>
                      {selection.isViable ? 'viable' : 'not viable'}
                    </span>
                    {selection.selectionScore !== null ? (
                      <span className="text-ink-3 num">Score {fmtNum(selection.selectionScore, 0)}</span>
                    ) : null}
                    {rankedExpiry ? (
                      <span className="text-ink-3 num">Ranked for {rankedExpiry}</span>
                    ) : null}
                  </div>

                  {!selection.isViable && selection.nonViabilityReasons.length > 0 ? (
                    <ul className="m-0 pl-4 text-ink-2 space-y-0.5">
                      {selection.nonViabilityReasons.map((r) => (
                        <li key={r}>{r}</li>
                      ))}
                    </ul>
                  ) : null}

                  {selection.selectionRationale.length > 0 ? (
                    <ul className="m-0 pl-4 text-ink-3 space-y-0.5">
                      {selection.selectionRationale.slice(0, 4).map((r) => (
                        <li key={r}>{r}</li>
                      ))}
                    </ul>
                  ) : null}

                  {rankedCandidates.length > 0 ? (
                    <div className="tbl-wrap">
                      <table className="tbl num">
                        <thead>
                          <tr>
                            <th className="r">Strike</th>
                            <th>Type</th>
                            <th className="r">Premium</th>
                            <th className="r">Score</th>
                            <th className="r">Net R:R</th>
                            <th>Standing</th>
                          </tr>
                        </thead>
                        <tbody>
                          {rankedCandidates.map((c) => (
                            <tr
                              key={`${c.strike}-${c.option_type}`}
                              className={c.strike === selection.selectedStrike ? 'bg-warn-wash' : undefined}
                            >
                              <td className="r">{Math.round(c.strike)}</td>
                              <td>{STRIKE_TYPE_LABELS[c.strike_type] ?? humanize(c.strike_type)}</td>
                              <td className="r">{c.market_premium !== null ? fmtNum(c.market_premium, 1) : '—'}</td>
                              <td className="r">{c.score !== null ? fmtNum(c.score, 0) : '—'}</td>
                              <td className="r">{c.net_rr_ratio !== null ? fmtNum(c.net_rr_ratio, 2) : '—'}</td>
                              <td>
                                <span className={`chip ${c.is_acceptable ? 'chip--up' : 'chip--neut'}`}>
                                  {c.is_acceptable ? 'acceptable' : 'rejected'}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}

                  {afford ? (
                    <p className="m-0 text-ink-3 num">
                      Paper margin · needs {afford.requiredMargin !== null ? fmtINR(afford.requiredMargin) : '—'}
                      {' '}of {afford.availableMargin !== null ? fmtINR(afford.availableMargin) : '—'} available
                      {afford.affordable === true ? ' — affordable' : afford.affordable === false ? ' — short of margin' : ''}.
                    </p>
                  ) : null}
                  {affordNote ? (
                    <p className="m-0 text-ink-3 num" role="status">{affordNote}</p>
                  ) : null}
                </div>
              ) : null}

              {moveBand || moveNote ? (
                <div className="rounded-md border border-border bg-card p-3 text-xs space-y-1.5">
                  <span className="micro-label block">Expected move band</span>
                  {moveBand ? (
                    <p className="m-0 text-ink-2 num">
                      Move {moveBand.expectedMovePoints !== null ? fmtNum(moveBand.expectedMovePoints, 1) : '—'} pts
                      {' '}· range {moveBand.conservativeMovePoints !== null ? fmtNum(moveBand.conservativeMovePoints, 1) : '—'}
                      {' / '}{moveBand.aggressiveMovePoints !== null ? fmtNum(moveBand.aggressiveMovePoints, 1) : '—'} pts
                      {moveBand.expectedDurationHours !== null ? ` · about ${fmtNum(moveBand.expectedDurationHours, 1)}h` : ''}
                      {moveBand.fastEnough === true ? ' · fast enough for the option' : moveBand.fastEnough === false ? ' · slow for the option' : ''}.
                    </p>
                  ) : null}
                  {moveBand?.velocityAssessment ? (
                    <p className="m-0 text-ink-3">{moveBand.velocityAssessment}</p>
                  ) : null}
                  {moveNote ? <p className="m-0 text-ink-3">{moveNote}</p> : null}
                </div>
              ) : null}

              {scenarios || simNote ? (
                <div className="rounded-md border border-border bg-card p-3 text-xs space-y-2">
                  <span className="micro-label block">Path scenarios · net of friction</span>
                  {scenarios ? (
                    <div className="tbl-wrap">
                      <table className="tbl num">
                        <thead>
                          <tr>
                            <th>Scenario</th>
                            <th className="r">Exit</th>
                            <th className="r">Net P&amp;L</th>
                            <th className="r">Return</th>
                            <th>Outcome</th>
                          </tr>
                        </thead>
                        <tbody>
                          {scenarios.map((s) => (
                            <tr key={s.label}>
                              <td>{s.label}</td>
                              <td className="r">{s.exit !== null ? fmtNum(s.exit, 1) : '—'}</td>
                              <td className="r">{s.netPnl !== null ? fmtINR(s.netPnl) : '—'}</td>
                              <td className="r">{s.netReturnPct !== null ? `${fmtNum(s.netReturnPct, 1)}%` : '—'}</td>
                              <td>
                                {s.profitable === null ? (
                                  '—'
                                ) : (
                                  <span className={`chip ${s.profitable ? 'chip--up' : 'chip--down'}`}>
                                    {s.profitable ? 'profit' : 'loss'}
                                  </span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}
                  {simNote ? <p className="m-0 text-ink-3">{simNote}</p> : null}
                </div>
              ) : null}
            </div>
          ) : null}

          {tab === 'whatif' ? (
            <div className="space-y-4 p-4 font-mono text-xs">
              {/* Portfolio Greeks Overview */}
              <div className="rounded-md border border-border bg-card p-3.5 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="micro-label">Portfolio Greeks Exposure</span>
                  {portfolioGreeksLoading ? <span className="text-ink-3">updating…</span> : null}
                </div>
                {portfolioGreeks ? (
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 num">
                    <div className="p-2 rounded bg-surface-subtle border border-border">
                      <span className="micro-label block">Total Delta</span>
                      <span className="text-sm font-semibold text-foreground">
                        {typeof portfolioGreeks.total_delta === 'number' ? fmtNum(portfolioGreeks.total_delta, 2) : '—'}
                      </span>
                    </div>
                    <div className="p-2 rounded bg-surface-subtle border border-border">
                      <span className="micro-label block">Total Gamma</span>
                      <span className="text-sm font-semibold text-foreground">
                        {typeof portfolioGreeks.total_gamma === 'number' ? fmtNum(portfolioGreeks.total_gamma, 4) : '—'}
                      </span>
                    </div>
                    <div className="p-2 rounded bg-surface-subtle border border-border">
                      <span className="micro-label block">Total Theta (/day)</span>
                      <span className="text-sm font-semibold text-foreground">
                        {typeof portfolioGreeks.total_theta_day === 'number' ? fmtINR(portfolioGreeks.total_theta_day) : '—'}
                      </span>
                    </div>
                    <div className="p-2 rounded bg-surface-subtle border border-border">
                      <span className="micro-label block">Total Vega (/1% IV)</span>
                      <span className="text-sm font-semibold text-foreground">
                        {typeof portfolioGreeks.total_vega === 'number' ? fmtINR(portfolioGreeks.total_vega) : '—'}
                      </span>
                    </div>
                  </div>
                ) : (
                  <p
                    className={`m-0 text-xs ${portfolioGreeksError ? 'text-down-strong' : 'text-ink-3'}`}
                    role={portfolioGreeksError ? 'alert' : undefined}
                  >
                    {portfolioGreeksLoading
                      ? 'Loading portfolio Greeks…'
                      : portfolioGreeksError
                        ? `Portfolio Greeks unavailable — ${portfolioGreeksError}`
                        : 'No open options positions to calculate portfolio Greeks.'}
                  </p>
                )}
              </div>

              {/* Interactive Greeks Calculator & IV Solver Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* 1. Black-Scholes Greeks Calculator */}
                <div className="rounded-md border border-border bg-card p-3.5 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="micro-label">Greeks Calculator</span>
                    <div className="flex gap-1">
                      <button
                        type="button"
                        onClick={() => setCalcType('CE')}
                        className={`px-2 py-0.5 rounded text-2xs font-semibold ${calcType === 'CE' ? 'bg-up/20 text-up-strong border border-up/40' : 'bg-surface-subtle text-ink-3'}`}
                      >
                        Call (CE)
                      </button>
                      <button
                        type="button"
                        onClick={() => setCalcType('PE')}
                        className={`px-2 py-0.5 rounded text-2xs font-semibold ${calcType === 'PE' ? 'bg-down/20 text-down-strong border border-down/40' : 'bg-surface-subtle text-ink-3'}`}
                      >
                        Put (PE)
                      </button>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-2xs text-ink-3 block mb-0.5">Spot price</label>
                      <input
                        type="number"
                        value={calcSpot}
                        onChange={(e) => setCalcSpot(e.target.value)}
                        className="w-full text-xs px-2 py-1 rounded border border-border bg-surface-subtle text-foreground"
                      />
                    </div>
                    <div>
                      <label className="text-2xs text-ink-3 block mb-0.5">Strike</label>
                      <input
                        type="number"
                        value={calcStrike}
                        onChange={(e) => setCalcStrike(e.target.value)}
                        className="w-full text-xs px-2 py-1 rounded border border-border bg-surface-subtle text-foreground"
                      />
                    </div>
                    <div>
                      <label className="text-2xs text-ink-3 block mb-0.5">DTE (days)</label>
                      <input
                        type="number"
                        value={calcDte}
                        onChange={(e) => setCalcDte(e.target.value)}
                        className="w-full text-xs px-2 py-1 rounded border border-border bg-surface-subtle text-foreground"
                      />
                    </div>
                    <div>
                      <label className="text-2xs text-ink-3 block mb-0.5">IV (%)</label>
                      <input
                        type="number"
                        value={calcIv}
                        onChange={(e) => setCalcIv(e.target.value)}
                        className="w-full text-xs px-2 py-1 rounded border border-border bg-surface-subtle text-foreground"
                      />
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={handleCalculateGreeks}
                    disabled={calcGreeksBusy}
                    className="w-full btn btn-primary text-xs py-1.5"
                  >
                    {calcGreeksBusy ? 'Computing…' : 'Compute Greeks'}
                  </button>

                  {calcGreeksError ? (
                    <p className="text-bear-strong text-2xs m-0">{calcGreeksError}</p>
                  ) : null}

                  {calcGreeksResult ? (
                    <div className="p-2.5 rounded bg-surface-subtle border border-border space-y-1.5 num">
                      <div className="flex justify-between text-xs font-semibold">
                        <span className="text-ink-2">Theoretical Price</span>
                        <span className="text-foreground">
                          {asNum(calcGreeksResult.theoretical_price) !== null
                            ? fmtINR(calcGreeksResult.theoretical_price)
                            : asNum(calcGreeksResult.price) !== null
                              ? fmtINR(calcGreeksResult.price)
                              : asNum(calcGreeksResult.premium) !== null
                                ? fmtINR(calcGreeksResult.premium)
                                : '—'}
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-x-2 gap-y-1 text-2xs text-ink-2 pt-1 border-t border-border">
                        <div className="flex justify-between">
                          <span>Delta:</span>
                          <span className="font-semibold text-foreground">{fmtNum(calcGreeksResult.delta, 4)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span>Gamma:</span>
                          <span className="font-semibold text-foreground">{fmtNum(calcGreeksResult.gamma, 5)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span>Theta:</span>
                          <span className="font-semibold text-foreground">
                            {fmtNum(
                              asNum(calcGreeksResult.theta_day) !== null ? calcGreeksResult.theta_day : calcGreeksResult.theta,
                              3,
                            )}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span>Vega:</span>
                          <span className="font-semibold text-foreground">{fmtNum(calcGreeksResult.vega, 3)}</span>
                        </div>
                        {calcGreeksResult.rho !== undefined ? (
                          <div className="flex justify-between">
                            <span>Rho:</span>
                            <span className="font-semibold text-foreground">{fmtNum(calcGreeksResult.rho, 4)}</span>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                </div>

                {/* 2. Implied Volatility Solver */}
                <div className="rounded-md border border-border bg-card p-3.5 space-y-3">
                  <span className="micro-label block">Implied Volatility Solver</span>

                  <div className="space-y-2">
                    <div>
                      <label className="text-2xs text-ink-3 block mb-0.5">Market Option Premium (₹)</label>
                      <input
                        type="number"
                        placeholder="e.g. 145.50"
                        value={solvePrice}
                        onChange={(e) => setSolvePrice(e.target.value)}
                        className="w-full text-xs px-2 py-1 rounded border border-border bg-surface-subtle text-foreground"
                      />
                    </div>
                    <p className="text-2xs text-ink-3 m-0">
                      Using spot {calcSpot || '—'}, strike {calcStrike || '—'}, DTE {calcDte}d for {calcType}.
                    </p>
                  </div>

                  <button
                    type="button"
                    onClick={handleSolveIV}
                    disabled={solveIvBusy || !solvePrice}
                    className="w-full btn text-xs py-1.5"
                  >
                    {solveIvBusy ? 'Solving IV…' : 'Solve Implied Volatility'}
                  </button>

                  {solveIvError ? (
                    <p className="text-bear-strong text-2xs m-0">{solveIvError}</p>
                  ) : null}

                  {solveIvResult ? (
                    <div className="p-2.5 rounded bg-surface-subtle border border-border space-y-1 num">
                      <div className="flex justify-between text-xs font-semibold">
                        <span className="text-ink-2">Solved IV</span>
                        <span className="text-accent-strong text-sm">
                          {typeof solveIvResult.iv === 'number'
                            ? `${fmtNum(solveIvResult.iv > 1 ? solveIvResult.iv : solveIvResult.iv * 100, 2)}%`
                            : typeof solveIvResult.implied_volatility === 'number'
                              ? `${fmtNum(solveIvResult.implied_volatility > 1 ? solveIvResult.implied_volatility : solveIvResult.implied_volatility * 100, 2)}%`
                              : '—'}
                        </span>
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          ) : null}
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-border bg-surface-subtle flex items-center justify-between text-xs text-ink-3 font-mono">
          <span>Press ESC or click close to return to War Room</span>
          <a
            href="/options"
            className="flex items-center gap-1 text-accent-strong font-semibold hover:underline"
          >
            <span>Full Options Desk</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>
    </div>
  );
});

'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { safeNum } from '@/lib/utils';
import type {
  QuantDataset,
  G0Result,
  G1Report,
  G2Report,
  OptionsSimResult,
  OptionsSpreadSimulationResult,
  StrategyMatrixRow,
  S6BatteryResult,
  S6TrackMetrics,
  S6Trial,
} from '@/lib/api/quant';
import { runStrategyMatrix, quantApi } from '@/lib/api/quant';
import {
  Activity,
  Shield,
  ShieldAlert,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Lock,
  Play,
  Layers,
  Scale,
  Sparkles,
  TableProperties,
  Loader2,
  Database,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';

const INITIAL_MATRIX_ROWS: StrategyMatrixRow[] = [
  {
    strategy_key: 'S1',
    strategy_name: 'Opening Range Breakout (ORB)',
    total_trades: 0,
    win_rate: 0,
    gross_expectancy_pct: 0,
    net_expectancy_pct: 0,
    profit_factor: 0,
    max_drawdown_pct: 0,
    gate_g0_verdict: 'NOT RUN',
  },
  {
    strategy_key: 'S2',
    strategy_name: '20-bar Momentum Breakout',
    total_trades: 0,
    win_rate: 0,
    gross_expectancy_pct: 0,
    net_expectancy_pct: 0,
    profit_factor: 0,
    max_drawdown_pct: 0,
    gate_g0_verdict: 'NOT RUN',
  },
  {
    strategy_key: 'S3',
    strategy_name: 'VWAP Reclaim / Reject',
    total_trades: 0,
    win_rate: 0,
    gross_expectancy_pct: 0,
    net_expectancy_pct: 0,
    profit_factor: 0,
    max_drawdown_pct: 0,
    gate_g0_verdict: 'NOT RUN',
  },
  {
    strategy_key: 'S4',
    strategy_name: 'Volatility Squeeze Breakout',
    total_trades: 0,
    win_rate: 0,
    gross_expectancy_pct: 0,
    net_expectancy_pct: 0,
    profit_factor: 0,
    max_drawdown_pct: 0,
    gate_g0_verdict: 'NOT RUN',
  },
  {
    strategy_key: 'S5',
    strategy_name: 'Structural Volume & Absorption Breakout',
    total_trades: 0,
    win_rate: 0,
    gross_expectancy_pct: 0,
    net_expectancy_pct: 0,
    profit_factor: 0,
    max_drawdown_pct: 0,
    gate_g0_verdict: 'NOT RUN',
  },
  {
    strategy_key: 'S6-A',
    strategy_name: 'S6-A: Compression Breakout (Continuation)',
    total_trades: 0,
    win_rate: 0,
    gross_expectancy_pct: 0,
    net_expectancy_pct: 0,
    profit_factor: 0,
    max_drawdown_pct: 0,
    gate_g0_verdict: 'NOT RUN',
  },
  {
    strategy_key: 'S6-F',
    strategy_name: 'S6-F: Failed Breakout Reversal',
    total_trades: 0,
    win_rate: 0,
    gross_expectancy_pct: 0,
    net_expectancy_pct: 0,
    profit_factor: 0,
    max_drawdown_pct: 0,
    gate_g0_verdict: 'NOT RUN',
  },
  {
    strategy_key: 'S7',
    strategy_name: 'Structural Absorption Reversal',
    total_trades: 0,
    win_rate: 0,
    gross_expectancy_pct: 0,
    net_expectancy_pct: 0,
    profit_factor: 0,
    max_drawdown_pct: 0,
    gate_g0_verdict: 'NOT RUN',
  },
  {
    strategy_key: 'S8',
    strategy_name: 'IV Regime Mispricing (S8SPEC_v1.0)',
    total_trades: 0,
    win_rate: 0,
    gross_expectancy_pct: 0,
    net_expectancy_pct: 0,
    profit_factor: 0,
    max_drawdown_pct: 0,
    gate_g0_verdict: 'NOT RUN',
  },
  {
    strategy_key: 'S4+S8',
    strategy_name: 'S4+S8 Confluence (Squeeze + IV Agreement)',
    total_trades: 0,
    win_rate: 0,
    gross_expectancy_pct: 0,
    net_expectancy_pct: 0,
    profit_factor: 0,
    max_drawdown_pct: 0,
    gate_g0_verdict: 'NOT RUN',
  },
  {
    strategy_key: 'S1+S3',
    strategy_name: 'S1+S3 Confluence (ORB + VWAP Agreement)',
    total_trades: 0,
    win_rate: 0,
    gross_expectancy_pct: 0,
    net_expectancy_pct: 0,
    profit_factor: 0,
    max_drawdown_pct: 0,
    gate_g0_verdict: 'NOT RUN',
  },
  {
    strategy_key: 'ALL',
    strategy_name: 'Portfolio Combination (S1-S5, S7-S8)',
    total_trades: 0,
    win_rate: 0,
    gross_expectancy_pct: 0,
    net_expectancy_pct: 0,
    profit_factor: 0,
    max_drawdown_pct: 0,
    gate_g0_verdict: 'NOT RUN',
  },
];

/** Strict finite-number parse for simulator inputs — blank is absent, never 0. */
function toFiniteNumber(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === '') return null;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : null;
}

export function QuantFalsificationPanel() {
  const [datasets, setDatasets] = useState<QuantDataset[]>([]);
  const [datasetsError, setDatasetsError] = useState<string | null>(null);
  const [loadingDatasets, setLoadingDatasets] = useState(false);
  const [symbol, setSymbol] = useState('sensex');
  const [timeframe, setTimeframe] = useState('15m');
  const [strategy, setStrategy] = useState('S6_A');
  const [kTp, setKTp] = useState(2.5);
  const [kSl, setKSl] = useState(1.0);
  const [sessionFilter, setSessionFilter] = useState(false);

  // Strategy Isolation Matrix State
  const [matrixLoading, setMatrixLoading] = useState(false);
  const [matrixRows, setMatrixRows] = useState<StrategyMatrixRow[]>(INITIAL_MATRIX_ROWS);
  const [matrixEvaluated, setMatrixEvaluated] = useState(false);
  const [matrixParams, setMatrixParams] = useState<string | null>(null);
  const [matrixError, setMatrixError] = useState<string | null>(null);

  // S6 Signature Strategy State
  const [s6BatteryLoading, setS6BatteryLoading] = useState(false);
  const [s6BatteryResult, setS6BatteryResult] = useState<S6BatteryResult | null>(null);
  const [s6BatteryError, setS6BatteryError] = useState<string | null>(null);
  const [s6Trials, setS6Trials] = useState<S6Trial[]>([]);
  const [loadingS6Trials, setLoadingS6Trials] = useState(false);
  const [showS6Trials, setShowS6Trials] = useState(false);

  // G0 State
  const [g0Loading, setG0Loading] = useState(false);
  const [g0Result, setG0Result] = useState<G0Result | null>(null);
  const [g0Error, setG0Error] = useState<string | null>(null);

  // G1 State
  const [g1Loading, setG1Loading] = useState(false);
  const [g1Report, setG1Report] = useState<G1Report | null>(null);
  const [g1Error, setG1Error] = useState<string | null>(null);

  // G2 State
  const [g2Loading, setG2Loading] = useState(false);
  const [g2Report, setG2Report] = useState<G2Report | null>(null);
  const [g2Error, setG2Error] = useState<string | null>(null);

  // Export State
  const [exportLoading, setExportLoading] = useState<'matrix' | 'trades' | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  // Options Sim State
  const [optionsLoading, setOptionsLoading] = useState(false);
  const [optionsResult, setOptionsResult] = useState<OptionsSimResult | null>(null);
  const [spreadMode, setSpreadMode] = useState<'naked' | 'spread'>('naked');
  const [spreadResult, setSpreadResult] = useState<OptionsSpreadSimulationResult | null>(null);
  const [simError, setSimError] = useState<string | null>(null);
  const [simSpotEntry, setSimSpotEntry] = useState('');
  const [simIvPct, setSimIvPct] = useState('');
  const [simStrikeWidth, setSimStrikeWidth] = useState('');
  const [simDte, setSimDte] = useState('');
  const [simHoldingBars, setSimHoldingBars] = useState('');
  const [simBarMinutes, setSimBarMinutes] = useState('');
  const [simSpotMove, setSimSpotMove] = useState('');
  const [simDemo, setSimDemo] = useState(false);
  const [simSubmitted, setSimSubmitted] = useState<{
    demo: boolean;
    spotEntry: number;
    ivPct: number;
    strikeWidth: number;
    dte: number;
    holdingBars: number;
    barMinutes: number;
    move: number;
  } | null>(null);

  const DEMO_SIM_INPUTS = {
    spotEntry: '80000',
    ivPct: '14',
    strikeWidth: '300',
    dte: '4',
    holdingBars: '6',
    barMinutes: '15',
    move: '300',
  };

  const toggleSimDemo = (checked: boolean) => {
    setSimDemo(checked);
    if (checked) {
      setSimSpotEntry(DEMO_SIM_INPUTS.spotEntry);
      setSimIvPct(DEMO_SIM_INPUTS.ivPct);
      setSimStrikeWidth(DEMO_SIM_INPUTS.strikeWidth);
      setSimDte(DEMO_SIM_INPUTS.dte);
      setSimHoldingBars(DEMO_SIM_INPUTS.holdingBars);
      setSimBarMinutes(DEMO_SIM_INPUTS.barMinutes);
      setSimSpotMove(DEMO_SIM_INPUTS.move);
    }
  };

  useEffect(() => {
    async function loadS6Trials() {
      setLoadingS6Trials(true);
      try {
        const res = await quantApi.getS6Trials();
        if (res?.data?.trials) {
          setS6Trials(res.data.trials);
        }
      } catch (err) {
        console.warn('Failed to load S6 trials:', err);
      } finally {
        setLoadingS6Trials(false);
      }
    }
    loadS6Trials();
  }, []);

  useEffect(() => {
    async function loadDatasets() {
      setLoadingDatasets(true);
      setDatasetsError(null);
      try {
        const res = await api.listDatasets();
        setDatasets(res.data || []);
      } catch (err: any) {
        setDatasets([]);
        setDatasetsError(err?.message || 'Failed to load local datasets');
        console.warn('Failed to load datasets', err);
      } finally {
        setLoadingDatasets(false);
      }
    }
    loadDatasets();
  }, []);

  const runMatrixFallback = async () => {
    const strats = [
      { key: 'S1', name: 'Opening Range Breakout (ORB)' },
      { key: 'S2', name: '20-bar Momentum Breakout' },
      { key: 'S3', name: 'VWAP Reclaim / Reject' },
      { key: 'S4', name: 'Volatility Squeeze Breakout' },
      { key: 'S5', name: 'Structural Volume & Absorption Breakout' },
      { key: 'S6-A', name: 'S6-A: Compression Breakout (Continuation)' },
      { key: 'S6-F', name: 'S6-F: Failed Breakout Reversal' },
      { key: 'S7', name: 'Structural Absorption Reversal' },
      { key: 'S8', name: 'IV Regime Mispricing (S8SPEC_v1.0)' },
      { key: 'S4+S8', name: 'S4+S8 Confluence (Squeeze + IV Agreement)' },
      { key: 'S1+S3', name: 'S1+S3 Confluence (ORB + VWAP Agreement)' },
      { key: 'ALL', name: 'Portfolio Combination (S1-S5, S7-S8)' },
    ];
    const results: StrategyMatrixRow[] = [];
    for (const s of strats) {
      const res = await api.runG0Baseline({
        symbol,
        timeframe,
        strategy_key: s.key,
        trend_aligned: true,
        session_filter: sessionFilter,
        k_tp: kTp,
        k_sl: kSl,
      });
      const m = res.data.metrics;
      results.push({
        strategy_key: s.key,
        strategy_name: s.name,
        total_trades: m.total_trades,
        win_rate: m.win_rate,
        gross_expectancy_pct: m.gross_expectancy_pct,
        net_expectancy_pct: m.net_expectancy_pct,
        profit_factor: m.profit_factor,
        max_drawdown_pct: m.max_drawdown_pct,
        gate_g0_verdict: m.gate_g0_verdict,
        verdict_reasons: m.verdict_reasons,
      });
    }
    setMatrixRows(results);
    setMatrixEvaluated(true);
    setMatrixParams(`${symbol}-${timeframe}-${kTp}-${kSl}-${sessionFilter}`);
  };

  const handleRunS6Battery = async () => {
    try {
      setS6BatteryLoading(true);
      setS6BatteryError(null);
      const res = await quantApi.runS6Battery({
        instrument: symbol.toUpperCase(),
        track: 'ALL',
        mode: 'historical',
      });
      if (res?.data) {
        setS6BatteryResult(res.data);
      }
    } catch (err: any) {
      setS6BatteryError(err?.message || 'Failed to execute S6 battery');
    } finally {
      setS6BatteryLoading(false);
    }
  };

  const getTrackMetrics = (trackKey: string): Partial<S6TrackMetrics> | null => {
    if (s6BatteryResult?.matrix?.[trackKey]) {
      return s6BatteryResult.matrix[trackKey];
    }
    const match = s6Trials.find(
      (t) =>
        t.track.toUpperCase() === trackKey.toUpperCase() &&
        (t.instrument.toUpperCase() === symbol.toUpperCase() ||
          t.instrument.toUpperCase() === 'SENSEX') &&
        t.metrics,
    );
    if (match && match.metrics) {
      return match.metrics as unknown as S6TrackMetrics;
    }
    return null;
  };

  const handleRunMatrix = async () => {
    setMatrixLoading(true);
    setMatrixError(null);
    try {
      const res = await runStrategyMatrix({
        symbol,
        timeframe,
        trend_aligned: true,
        session_filter: sessionFilter,
        k_tp: kTp,
        k_sl: kSl,
        stress_multiplier: 1.0,
      });
      const rawRows: StrategyMatrixRow[] =
        res.data?.matrix ||
        res.data?.rows ||
        res.matrix ||
        res.rows ||
        (Array.isArray(res.data) ? res.data : []);

      if (rawRows && rawRows.length > 0) {
        setMatrixRows(rawRows);
        setMatrixEvaluated(true);
        setMatrixParams(`${symbol}-${timeframe}-${kTp}-${kSl}-${sessionFilter}`);
      } else {
        await runMatrixFallback();
      }
    } catch (err: any) {
      try {
        await runMatrixFallback();
      } catch {
        setMatrixError(err.message || 'Failed to evaluate strategy isolation matrix');
      }
    } finally {
      setMatrixLoading(false);
    }
  };

  const handleRunG0 = async () => {
    setG0Loading(true);
    setG0Error(null);
    try {
      const res = await api.runG0Baseline({
        symbol,
        timeframe,
        strategy_key: strategy,
        trend_aligned: true,
        session_filter: sessionFilter,
        k_tp: kTp,
        k_sl: kSl,
      });
      setG0Result(res.data);
    } catch (err: any) {
      setG0Error(err.message || 'Gate G0 baseline run failed');
    } finally {
      setG0Loading(false);
    }
  };

  const handleRunG1 = async () => {
    setG1Loading(true);
    setG1Error(null);
    try {
      const res = await api.runG1Ablation({
        symbol,
        timeframe,
        strategy_key: strategy,
        n_folds: 5,
        confidence_threshold: 0.38,
        max_disagreement: 0.30,
        k_tp: kTp,
        k_sl: kSl,
      });
      setG1Report(res.data);
    } catch (err: any) {
      setG1Error(err.message || 'Gate G1 walk-forward ablation failed');
    } finally {
      setG1Loading(false);
    }
  };

  const handleRunG2 = async () => {
    setG2Loading(true);
    setG2Error(null);
    try {
      const res = await quantApi.runG2Robustness({
        symbol,
        timeframe,
        strategy_key: strategy,
        k_tp: kTp,
        k_sl: kSl,
        t_max_bars: 12,
        trend_aligned: true,
        session_filter: sessionFilter,
      });
      setG2Report(res.data);
    } catch (err: any) {
      setG2Error(err.message || 'Gate G2 robustness evaluation failed');
    } finally {
      setG2Loading(false);
    }
  };

  const downloadCsv = (csv: string, filename: string) => {
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleExportMatrix = async () => {
    setExportLoading('matrix');
    setExportError(null);
    try {
      const res = await quantApi.exportStrategyMatrix({
        symbol,
        timeframe,
        trend_aligned: true,
        session_filter: sessionFilter,
        k_tp: kTp,
        k_sl: kSl,
        stress_multiplier: 1.0,
      });
      if (res?.data?.csv) downloadCsv(res.data.csv, res.data.filename || 'strategy_matrix.csv');
    } catch (err: any) {
      setExportError(err.message || 'Matrix CSV export failed');
    } finally {
      setExportLoading(null);
    }
  };

  const handleExportG0Trades = async () => {
    setExportLoading('trades');
    setExportError(null);
    try {
      const res = await quantApi.exportG0Trades({
        symbol,
        timeframe,
        strategy_key: strategy,
        trend_aligned: true,
        session_filter: sessionFilter,
        k_tp: kTp,
        k_sl: kSl,
        t_max_bars: 12,
        stress_multiplier: 1.0,
      });
      if (res?.data?.csv) downloadCsv(res.data.csv, res.data.filename || 'g0_trades.csv');
    } catch (err: any) {
      setExportError(err.message || 'G0 trades CSV export failed');
    } finally {
      setExportLoading(null);
    }
  };

  const handleSimulateOptions = async () => {
    const spotEntryNum = toFiniteNumber(simSpotEntry);
    const ivPctNum = toFiniteNumber(simIvPct);
    const strikeWidthNum = toFiniteNumber(simStrikeWidth);
    const dteNum = toFiniteNumber(simDte);
    const holdingBarsNum = toFiniteNumber(simHoldingBars);
    const barMinutesNum = toFiniteNumber(simBarMinutes);
    const moveNum = toFiniteNumber(simSpotMove);

    const missing: string[] = [];
    if (spotEntryNum === null) missing.push('spot entry');
    if (ivPctNum === null) missing.push('IV %');
    if (strikeWidthNum === null) missing.push('strike width');
    if (dteNum === null) missing.push('DTE');
    if (holdingBarsNum === null) missing.push('holding bars');
    if (barMinutesNum === null) missing.push('bar minutes');
    if (moveNum === null) missing.push('spot move');

    if (
      missing.length > 0 ||
      spotEntryNum === null ||
      ivPctNum === null ||
      strikeWidthNum === null ||
      dteNum === null ||
      holdingBarsNum === null ||
      barMinutesNum === null ||
      moveNum === null
    ) {
      setSpreadResult(null);
      setOptionsResult(null);
      setSimError(
        `Simulator inputs required: ${missing.join(', ')}. No defaults are assumed — enable "Demo inputs" to run a clearly-labelled illustration.`,
      );
      return;
    }

    setSimError(null);
    setOptionsLoading(true);
    try {
      if (spreadMode === 'spread') {
        const res = await quantApi.simulateOptionsSpread({
          symbol: symbol.toUpperCase(),
          direction: moveNum >= 0 ? 'LONG' : 'SHORT',
          spot_entry: spotEntryNum,
          spot_exit: spotEntryNum + moveNum,
          holding_bars: Math.round(holdingBarsNum),
          bar_minutes: Math.round(barMinutesNum),
          iv: ivPctNum / 100,
          dte_entry: dteNum,
          strike_width: strikeWidthNum,
        });
        setSpreadResult(res.data);
        setOptionsResult(null);
      } else {
        const res = await api.simulateOptionsTrade({
          symbol: symbol.toUpperCase(),
          direction: moveNum >= 0 ? 1 : -1,
          spot_entry: spotEntryNum,
          spot_exit: spotEntryNum + moveNum,
          bars_held: Math.round(holdingBarsNum),
          days_to_expiry: dteNum,
          custom_iv: ivPctNum / 100,
        });
        setOptionsResult(res.data);
        setSpreadResult(null);
      }
      setSimSubmitted({
        demo: simDemo,
        spotEntry: spotEntryNum,
        ivPct: ivPctNum,
        strikeWidth: strikeWidthNum,
        dte: dteNum,
        holdingBars: holdingBarsNum,
        barMinutes: barMinutesNum,
        move: moveNum,
      });
    } catch (err: any) {
      setSpreadResult(null);
      setOptionsResult(null);
      setSimError(err?.message || 'Options simulation failed');
    } finally {
      setOptionsLoading(false);
    }
  };

  // Dataset Provenance resolution — no cross-symbol or invented fallbacks.
  const matchedDataset =
    datasets.find(
      (d) => d.symbol.toLowerCase() === symbol.toLowerCase() && d.timeframe === '1m',
    ) ?? null;
  const datasetMissingReason = loadingDatasets
    ? 'Checking local dataset store…'
    : datasetsError
      ? `Dataset store unavailable: ${datasetsError}`
      : `No local 1m dataset registered for ${symbol.toUpperCase()} — run a historical download first.`;
  const sourceLabel = matchedDataset
    ? `Source: ${symbol.toUpperCase()} 1m (${matchedDataset.row_count.toLocaleString()} bars)`
    : `Source: ${symbol.toUpperCase()} 1m — Unavailable`;
  const analysisLabel = matchedDataset
    ? `Analysis: ${timeframe} (Resampled)`
    : `Analysis: ${timeframe} — Unavailable`;
  const qualityLabel = matchedDataset
    ? `Data Quality: ${matchedDataset.data_quality_score}/100${matchedDataset.data_quality_score >= 100 ? ' (Firewall Clean)' : ''}`
    : 'Data Quality: Unavailable';

  const isMatrixStale =
    matrixEvaluated && matrixParams !== `${symbol}-${timeframe}-${kTp}-${kSl}-${sessionFilter}`;

  // Gate G1 Blocked Condition:
  // If G0 status is failed or matrix has no passing baseline, ML is strictly blocked.
  const isG0Failed = g0Result?.metrics.gate_g0_verdict === 'FAILED';
  const hasPassingInMatrix = matrixEvaluated && matrixRows.some((r) => r.gate_g0_verdict === 'PASSED');
  const matrixEvaluatedAndFailed = matrixEvaluated && !hasPassingInMatrix;
  const hasPassedG0 = g0Result?.metrics.gate_g0_verdict === 'PASSED';

  const isG1Blocked = isG0Failed || matrixEvaluatedAndFailed || (!hasPassedG0 && !hasPassingInMatrix);
  const promotionEligible = hasPassedG0 || hasPassingInMatrix;

  // 4-Dimensional Institutional Governance Dimensions
  const researchVerdict = g0Result
    ? g0Result.metrics.gate_g0_verdict
    : matrixEvaluated
      ? hasPassingInMatrix
        ? 'VALIDATED'
        : matrixRows.some((r) => r.gate_g0_verdict === 'INCONCLUSIVE')
          ? 'INCONCLUSIVE'
          : 'FALSIFIED'
      : 'EXPLORATORY';

  const researchColor =
    researchVerdict === 'VALIDATED'
      ? 'text-up-strong'
      : researchVerdict === 'INCONCLUSIVE'
        ? 'text-warn-strong'
        : researchVerdict === 'FALSIFIED'
          ? 'text-down-strong'
          : 'text-accent';

  return (
    <div className="flex flex-col gap-4">
      {/* Institutional status: static build metadata is labelled as such; only
          research edge / promotion derive from evaluated payloads. */}
      <section aria-label="Institutional governance dimensions" className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
        <div className="card p-3 bg-surface border border-border rounded-lg shadow-sm flex flex-col justify-between">
          <span className="text-[10px] uppercase font-bold text-ink-2 tracking-wider">Engine (static build)</span>
          <span
            className="text-xs font-mono font-bold text-up-strong mt-1.5 flex items-center gap-1.5"
            title="Static build metadata — the research engine ships with this bundle. This is not a live runtime status."
          >
            <span className="size-2 rounded-full bg-up-strong inline-block" aria-hidden="true" /> IMPLEMENTED
          </span>
        </div>
        <div className="card p-3 bg-surface border border-border rounded-lg shadow-sm flex flex-col justify-between">
          <span className="text-[10px] uppercase font-bold text-ink-2 tracking-wider">Test suite (static build)</span>
          <span
            className="text-xs font-mono font-bold text-up-strong mt-1.5 flex items-center gap-1.5"
            title="Static build metadata — test count recorded when this bundle was produced, not a live test run."
          >
            <CheckCircle2 size={13} className="text-up-strong" /> 40/40 PASSING
          </span>
        </div>
        <div className="card p-3 bg-surface border border-border rounded-lg shadow-sm flex flex-col justify-between">
          <span className="text-[10px] uppercase font-bold text-ink-2 tracking-wider">Research edge (last run)</span>
          <span className={`text-xs font-mono font-bold mt-1.5 flex items-center gap-1.5 ${researchColor}`}>
            {researchVerdict === 'VALIDATED' && <CheckCircle2 size={13} />}
            {researchVerdict === 'INCONCLUSIVE' && <AlertCircle size={13} />}
            {researchVerdict === 'FALSIFIED' && <XCircle size={13} />}
            {researchVerdict === 'EXPLORATORY' && <AlertCircle size={13} />}
            {researchVerdict}
          </span>
        </div>
        <div className="card p-3 bg-surface border border-border rounded-lg shadow-sm flex flex-col justify-between">
          <span className="text-[10px] uppercase font-bold text-ink-2 tracking-wider">Promotion (last run)</span>
          <span
            className={`text-xs font-mono font-bold mt-1.5 flex items-center gap-1.5 ${
              promotionEligible ? 'text-warn-strong' : 'text-down-strong'
            }`}
            title={
              promotionEligible
                ? 'G0 edge survived — G1 and G2 gates are still required before promotion.'
                : 'No passing G0 evaluation yet — downstream ML and execution stay blocked.'
            }
          >
            <Lock size={12} className={promotionEligible ? 'text-warn-strong' : 'text-down-strong'} />
            {promotionEligible ? 'G1/G2 STILL REQUIRED' : 'BLOCKED (G0)'}
          </span>
        </div>
      </section>

      {/* Persistent Research Integrity Banner */}
      <aside
        aria-label="Experimental research protocol"
        className="p-4 bg-warn-wash border border-warn-line rounded-lg shadow-sm flex items-start gap-3"
      >
        <Shield className="size-5 text-warn-strong shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <h2 className="text-xs font-bold tracking-wider uppercase text-warn-strong">
            EXPERIMENTAL RESEARCH PROTOCOL
          </h2>
          <p className="text-xs text-ink-2 mt-1 leading-relaxed">
            Displayed metrics are empirical measurements under statutory Indian F&amp;O costs (STT, BSE turnover, SEBI, GST, ₹20 brokerage, slippage). Software correctness does not equal trading edge. Downstream ML (G1) and Execution (Tier 3) are strictly BLOCKED until base edge survives Gate G0.
          </p>
        </div>
      </aside>

      {/* Control Bar */}
      <section className="card p-4 bg-surface border border-border rounded-lg shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <div>
              <label className="text-xs text-ink-2 font-medium block mb-1">Underlying Asset</label>
              <select
                className="input w-auto"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
              >
                <option value="sensex">BSE SENSEX</option>
                <option value="nifty">NSE NIFTY 50</option>
              </select>
            </div>

            <div>
              <label className="text-xs text-ink-2 font-medium block mb-1">Resolution</label>
              <select
                className="input w-auto"
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
              >
                <option value="15m">15-minute (Resampled)</option>
                <option value="5m">5-minute (Resampled)</option>
                <option value="1m">1-minute (Raw Ticks)</option>
              </select>
            </div>

            <div>
              <label className="text-xs text-ink-2 font-medium block mb-1">Strategy Hypothesis</label>
              <select
                className="input w-auto"
                value={strategy}
                onChange={(e) => setStrategy(e.target.value)}
              >
                <option value="S6_A">S6-A: Compression Breakout (Continuation)</option>
                <option value="S6_F">S6-F: Failed Breakout Reversal</option>
                <option value="S7">S7: Structural Absorption Reversal</option>
                <option value="S8">S8: IV Regime Mispricing</option>
                <option value="S4+S8">S4+S8: Squeeze + IV Confluence</option>
                <option value="S1+S3">S1+S3: ORB + VWAP Confluence</option>
                <option value="S4">S4: Volatility Squeeze Breakout</option>
                <option value="S5">S5: Structural Volume &amp; Absorption Breakout</option>
                <option value="S1">S1: Opening Range Breakout (ORB)</option>
                <option value="S2">S2: 20-bar Momentum Breakout</option>
                <option value="S3">S3: VWAP Reclaim / Reject</option>
                <option value="ALL">ALL Strategies (S1-S5, S7-S8)</option>
              </select>
            </div>

            <div>
              <label className="text-xs text-ink-2 font-medium block mb-1">Target (k_tp)</label>
              <input
                type="number"
                step="0.5"
                className="input input-sm bg-inset border-border-strong text-sm rounded px-2 py-1 w-20 font-mono"
                value={kTp}
                onChange={(e) => setKTp(Number(e.target.value))}
              />
            </div>

            <div>
              <label className="text-xs text-ink-2 font-medium block mb-1">Stop (k_sl)</label>
              <input
                type="number"
                step="0.25"
                className="input input-sm bg-inset border-border-strong text-sm rounded px-2 py-1 w-20 font-mono"
                value={kSl}
                onChange={(e) => setKSl(Number(e.target.value))}
              />
              {kSl < 0.75 && (
                <span className="text-[10px] text-warn-strong block mt-0.5 font-sans" title="Stop is narrower than intra-bar noise envelope and will trigger adverse stop-outs">
                  ⚠️ Sub-noise stop
                </span>
              )}
            </div>

            <div className="flex flex-col justify-end pb-1">
              <label className="flex items-center gap-1.5 cursor-pointer text-xs text-ink font-medium select-none">
                <input
                  type="checkbox"
                  className="checkbox checkbox-sm accent-accent"
                  checked={sessionFilter}
                  onChange={(e) => setSessionFilter(e.target.checked)}
                />
                <span>Session Filter</span>
              </label>
              <span className="text-[10px] text-ink-muted font-mono" title="09:20-10:30 & 14:15-15:15 IST">
                (09:20–10:30 &amp; 14:15–15:15)
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2 mt-2 sm:mt-0">
            <button
              type="button"
              className="btn btn-primary flex items-center gap-1.5 px-3 py-1.5 text-xs transition"
              disabled={g0Loading}
              onClick={handleRunG0}
            >
              <Play size={13} />
              {g0Loading ? 'Testing G0…' : 'Run Gate G0 Baseline'}
            </button>

            <button
              type="button"
              className={`btn flex items-center gap-1.5 px-3 py-1.5 text-xs transition ${
                isG1Blocked
                  ? 'bg-inset text-ink border border-border hover:bg-hover'
                  : 'btn-primary'
              }`}
              disabled={g1Loading}
              onClick={handleRunG1}
              title={
                isG1Blocked
                  ? 'G1 Research Mode: Exploratory offline study (Non-Promotable due to unqualified baseline).'
                  : 'Run Gate G1 Purged WFO Ablation'
              }
            >
              <Layers size={13} />
              {g1Loading ? 'Ablating G1…' : isG1Blocked ? 'Run G1 (Exploratory Study)' : 'Run Gate G1 Ablation'}
            </button>

            <button
              type="button"
              className="btn flex items-center gap-1.5 px-3 py-1.5 text-xs transition bg-inset text-ink border border-border hover:bg-hover"
              disabled={g2Loading}
              onClick={handleRunG2}
              title="Run Gate G2 cost-stress + parameter-sensitivity robustness"
            >
              <Shield size={13} />
              {g2Loading ? 'Testing G2…' : 'Run Gate G2 Robustness'}
            </button>
          </div>
        </div>

        {/* Dataset Provenance banner */}
        <div className="mt-3 pt-3 border-t border-border flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-1 font-semibold text-ink">
              <Activity size={12} className="text-accent" />
              Dataset Provenance:
            </span>
            {loadingDatasets ? (
              <span className="text-ink-2">Checking local storage…</span>
            ) : (
              <div className="flex flex-wrap items-center gap-2 font-mono">
                <span
                  className="badge bg-inset px-2.5 py-0.5 rounded text-ink border border-border"
                  title={matchedDataset ? undefined : datasetMissingReason}
                >
                  {sourceLabel}
                </span>
                <span
                  className={`badge px-2.5 py-0.5 rounded border font-semibold ${
                    matchedDataset
                      ? 'bg-accent-wash text-accent-strong border-accent-line'
                      : 'bg-inset text-ink-2 border-border'
                  }`}
                  title={matchedDataset ? undefined : datasetMissingReason}
                >
                  {analysisLabel}
                </span>
                <span
                  className={`badge px-2.5 py-0.5 rounded border font-semibold ${
                    matchedDataset
                      ? 'bg-up-wash text-up-strong border-up-line'
                      : 'bg-inset text-ink-2 border-border'
                  }`}
                  title={matchedDataset ? 'Dataset quality score reported by the local quant store.' : datasetMissingReason}
                >
                  {qualityLabel}
                </span>
                {!matchedDataset ? (
                  <span className="text-warn-strong font-sans">{datasetMissingReason}</span>
                ) : null}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Strategy Isolation Matrix Table */}
      <section className="card p-4 bg-surface border border-border rounded-lg shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <TableProperties size={16} className="text-accent" />
              <h3 className="text-sm font-semibold text-ink">
                STRATEGY ISOLATION BENCHMARK (GATE G0 PRE-REQUISITE)
              </h3>
              {isMatrixStale && (
                <span className="badge bg-warn-wash text-warn-strong border border-warn-line px-2 py-0.5 rounded text-[11px] font-sans font-medium">
                  Inputs Changed (Click Run to Update)
                </span>
              )}
            </div>
            <p className="text-xs text-ink-2 mt-0.5">
              Independent evaluation of individual hypotheses under identical execution assumptions before portfolio pooling or ML filtering.
            </p>
            {isMatrixStale && (
              <p className="text-[11px] text-warn-strong mt-1 font-medium font-sans">
                ⚠️ Table shows results from prior parameters. Click &ldquo;Run Strategy Isolation Matrix&rdquo; to re-calculate with current settings.
              </p>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            className="btn flex items-center gap-1.5 px-3 py-1.5 text-xs transition bg-inset text-ink border border-border hover:bg-hover"
            disabled={matrixLoading || exportLoading === 'matrix' || !matrixEvaluated}
            onClick={handleExportMatrix}
            title="Download the evaluated matrix as CSV"
          >
            {exportLoading === 'matrix' ? (
              <>
                <Loader2 size={13} className="animate-spin" />
                Exporting…
              </>
            ) : (
              <>
                <TableProperties size={13} />
                Export Matrix CSV
              </>
            )}
          </button>
          <button
            type="button"
            className="btn btn-primary flex items-center gap-1.5 px-3 py-1.5 text-xs transition shrink-0"
            disabled={matrixLoading}
            onClick={handleRunMatrix}
          >
            {matrixLoading ? (
              <>
                <Loader2 size={13} className="animate-spin" />
                Running Matrix…
              </>
            ) : (
              <>
                <Play size={13} />
                Run Strategy Isolation Matrix
              </>
            )}
          </button>
          </div>
        </div>

        {matrixError && (
          <div className="p-3 mb-3 bg-down-wash border border-down-line rounded text-down-strong text-xs flex items-center gap-2">
            <ShieldAlert size={14} />
            {matrixError}
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left border-collapse border border-border">
            <thead>
              <tr className="bg-surface-subtle text-ink-2 border-b border-border">
                <th className="p-2.5">Strategy</th>
                <th className="p-2.5 text-right">Trades</th>
                <th className="p-2.5 text-right">Win Rate</th>
                <th className="p-2.5 text-right">Gross Exp</th>
                <th className="p-2.5 text-right">Net Exp</th>
                <th className="p-2.5 text-right">Profit Factor</th>
                <th className="p-2.5 text-right">Max DD</th>
                <th className="p-2.5 text-center">Gate G0 Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border font-mono">
              {matrixRows.map((row) => {
                const isNotRun = row.gate_g0_verdict === 'NOT RUN';
                const isPassed = row.gate_g0_verdict === 'PASSED';
                const netExpColor = isNotRun
                  ? 'text-ink-2'
                  : row.net_expectancy_pct > 0
                    ? 'text-up-strong'
                    : 'text-down-strong';

                return (
                  <tr
                    key={row.strategy_key}
                    className={
                      row.strategy_key === 'ALL'
                        ? 'bg-surface-subtle font-semibold'
                        : 'hover:bg-hover'
                    }
                  >
                    <td className="p-2.5 font-sans">
                      <div className="flex items-center gap-1.5">
                        <span className="badge bg-inset px-1.5 py-0.5 rounded font-mono text-[11px] text-ink font-semibold">
                          {row.strategy_key}
                        </span>
                        <span className="text-ink text-xs">
                          {row.strategy_name || row.strategy_key}
                        </span>
                      </div>
                    </td>
                    <td className="p-2.5 text-right text-ink">
                      {isNotRun ? '—' : row.total_trades}
                    </td>
                    <td className="p-2.5 text-right text-ink">
                      {isNotRun ? '—' : `${(row.win_rate * 100).toFixed(1)}%`}
                    </td>
                    <td className="p-2.5 text-right text-ink">
                      {isNotRun
                        ? '—'
                        : `${row.gross_expectancy_pct >= 0 ? '+' : ''}${(row.gross_expectancy_pct * 100).toFixed(3)}%`}
                    </td>
                    <td className={`p-2.5 text-right font-bold ${netExpColor}`}>
                      {isNotRun
                        ? '—'
                        : `${row.net_expectancy_pct >= 0 ? '+' : ''}${(row.net_expectancy_pct * 100).toFixed(3)}%`}
                    </td>
                    <td className="p-2.5 text-right text-ink">
                      {isNotRun ? '—' : row.profit_factor.toFixed(2)}
                    </td>
                    <td className="p-2.5 text-right text-ink">
                      {isNotRun ? '—' : `${(row.max_drawdown_pct * 100).toFixed(1)}%`}
                    </td>
                    <td className="p-2.5 text-center">
                      {isNotRun ? (
                        <span className="badge bg-inset text-ink-2 border border-border px-2 py-0.5 rounded text-xs font-sans inline-flex items-center gap-1">
                          NOT RUN
                        </span>
                      ) : isPassed ? (
                        <span className="badge bg-up-wash text-up-strong border border-up-line px-2 py-0.5 rounded text-xs font-sans inline-flex items-center gap-1">
                          <CheckCircle2 size={12} /> PASSED
                        </span>
                      ) : row.gate_g0_verdict === 'INCONCLUSIVE' ? (
                        <span className="badge bg-warn-wash text-warn-strong border border-warn-line px-2 py-0.5 rounded text-xs font-sans inline-flex items-center gap-1" title="Sample underpowered (need >= 25 trades)">
                          <AlertCircle size={12} /> INCONCLUSIVE
                        </span>
                      ) : (
                        <span className="badge bg-down-wash text-down-strong border border-down-line px-2 py-0.5 rounded text-xs font-sans inline-flex items-center gap-1">
                          <XCircle size={12} /> FAILED
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Gate G0 Section */}
      {g0Error && (
        <div className="p-3 bg-down-wash border border-down-line rounded text-down-strong text-xs flex items-center gap-2">
          <ShieldAlert size={14} />
          {g0Error}
        </div>
      )}

      {g0Result && (
        <section className="card p-4 bg-surface border border-border rounded-lg">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-ink">Gate G0: Base Edge Falsification</h3>
              {g0Result.metrics.gate_g0_verdict === 'PASSED' ? (
                <span className="badge bg-up-wash text-up-strong border border-up-line px-2 py-0.5 rounded text-xs flex items-center gap-1">
                  <CheckCircle2 size={12} /> PASSED
                </span>
              ) : g0Result.metrics.gate_g0_verdict === 'INCONCLUSIVE' ? (
                <span className="badge bg-warn-wash text-warn-strong border border-warn-line px-2 py-0.5 rounded text-xs flex items-center gap-1">
                  <AlertCircle size={12} /> INCONCLUSIVE
                </span>
              ) : (
                <span className="badge bg-down-wash text-down-strong border border-down-line px-2 py-0.5 rounded text-xs flex items-center gap-1">
                  <XCircle size={12} /> FAILED
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-ink-2">
                Statutory Cost Friction:{' '}
                <b>
                  {(g0Result.metrics.cost_drag_pct * 100).toFixed(3)}% (
                  {(g0Result.metrics.cost_drag_pct * 10000).toFixed(1)} bps)
                </b>
              </span>
              <button
                type="button"
                className="btn flex items-center gap-1.5 px-2.5 py-1 text-xs transition bg-inset text-ink border border-border hover:bg-hover"
                disabled={exportLoading === 'trades'}
                onClick={handleExportG0Trades}
                title="Download G0 sample trades as CSV"
              >
                {exportLoading === 'trades' ? (
                  <>
                    <Loader2 size={12} className="animate-spin" />
                    Exporting…
                  </>
                ) : (
                  <>
                    <TableProperties size={12} />
                    Export Trades CSV
                  </>
                )}
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 mb-4">
            <div className="p-2.5 bg-surface-subtle rounded border border-border">
              <div className="text-xs text-ink-2">Total Trades</div>
              <div className="text-base font-bold text-ink font-mono mt-0.5">{g0Result.metrics.total_trades}</div>
            </div>
            <div className="p-2.5 bg-surface-subtle rounded border border-border">
              <div className="text-xs text-ink-2">Win Rate</div>
              <div className={`text-base font-bold font-mono mt-0.5 ${g0Result.metrics.win_rate >= 0.5 ? 'text-up-strong' : 'text-warn-strong'}`}>
                {(g0Result.metrics.win_rate * 100).toFixed(1)}%
              </div>
            </div>
            <div className="p-2.5 bg-surface-subtle rounded border border-border">
              <div className="text-xs text-ink-2">Gross Exp %</div>
              <div className="text-base font-bold text-ink font-mono mt-0.5">
                {(g0Result.metrics.gross_expectancy_pct * 100).toFixed(3)}%
              </div>
            </div>
            <div className="p-2.5 bg-surface-subtle rounded border border-border">
              <div className="text-xs text-ink-2">Net Exp %</div>
              <div className={`text-base font-bold font-mono mt-0.5 ${g0Result.metrics.net_expectancy_pct > 0 ? 'text-up-strong' : 'text-down-strong'}`}>
                {(g0Result.metrics.net_expectancy_pct * 100).toFixed(3)}%
              </div>
            </div>
            <div className="p-2.5 bg-surface-subtle rounded border border-border">
              <div className="text-xs text-ink-2">Profit Factor</div>
              <div className={`text-base font-bold font-mono mt-0.5 ${g0Result.metrics.profit_factor >= 1.1 ? 'text-up-strong' : 'text-down-strong'}`}>
                {g0Result.metrics.profit_factor.toFixed(2)}
              </div>
            </div>
            <div className="p-2.5 bg-surface-subtle rounded border border-border">
              <div className="text-xs text-ink-2">Max DD %</div>
              <div className="text-base font-bold text-ink font-mono mt-0.5">
                {(g0Result.metrics.max_drawdown_pct * 100).toFixed(1)}%
              </div>
            </div>
            <div className="p-2.5 bg-surface-subtle rounded border border-border">
              <div className="text-xs text-ink-2">Deflated Sharpe</div>
              <div className="text-base font-bold text-ink font-mono mt-0.5">
                {g0Result.metrics.deflated_sharpe_ratio.toFixed(2)}
              </div>
            </div>
          </div>

          <div className="p-3 bg-surface-subtle rounded border border-border text-xs">
            <div className="font-semibold text-ink-2 mb-1">Gate Evaluation Diagnostic:</div>
            <ul className="list-disc list-inside space-y-0.5 text-ink-2">
              {g0Result.metrics.verdict_reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {/* S6 Signature Strategy: Adaptive Compression-Expansion Breakout Section */}
      <section className="card p-4 bg-surface border border-border rounded-lg shadow-sm" aria-label="S6 Signature Strategy">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <Sparkles size={16} className="text-accent" />
              <h3 className="text-sm font-semibold text-ink">
                DROID SIGNATURE STRATEGY S6: ADAPTIVE COMPRESSION-EXPANSION BREAKOUT
              </h3>
              <span className="badge bg-warn-wash text-warn-strong border border-warn-line px-2 py-0.5 rounded text-[11px] font-sans font-medium">
                EXPERIMENTAL
              </span>
              <span className="badge bg-down-wash text-down-strong border border-down-line px-2 py-0.5 rounded text-[11px] font-sans font-medium">
                <Lock size={10} className="inline mr-1" />
                BLOCKED (G0)
              </span>
              <span className="badge bg-inset text-ink border border-border px-2 py-0.5 rounded text-[11px] font-mono">
                S6SPEC_v1.3
              </span>
            </div>
            <p className="text-xs text-ink-2 mt-1">
              Empirical multi-timeframe research pipeline testing 5m volatility compression persistence, expansion breakouts, and rapid structural failure reversals under statutory friction.
            </p>
          </div>
          <button
            type="button"
            className="btn btn-primary flex items-center gap-1.5 px-3 py-1.5 text-xs transition shrink-0"
            disabled={s6BatteryLoading}
            onClick={handleRunS6Battery}
          >
            {s6BatteryLoading ? (
              <>
                <Loader2 size={13} className="animate-spin" />
                Running S6 2×2 Battery…
              </>
            ) : (
              <>
                <Play size={13} />
                Run S6 Triage Battery ({symbol.toUpperCase()})
              </>
            )}
          </button>
        </div>

        {s6BatteryError && (
          <div className="p-3 mb-3 bg-down-wash border border-down-line rounded text-down-strong text-xs flex items-center gap-2">
            <ShieldAlert size={14} />
            {s6BatteryError}
          </div>
        )}

        {/* 2x2 Core Research Matrix Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
          {[
            {
              trackKey: 'S6A_T1',
              title: 'Track A: S6-A / T1',
              subtitle: '5m Context + 1m Breakout + 1m Execution (Continuation)',
              variant: 'S6-A',
              tf: '1m',
            },
            {
              trackKey: 'S6A_T4',
              title: 'Track B: S6-A / T4',
              subtitle: '5m Context + 5m Breakout + 5m Execution (Continuation)',
              variant: 'S6-A',
              tf: '5m',
            },
            {
              trackKey: 'S6F_T1',
              title: 'Track C: S6-F / T1',
              subtitle: '5m Context + 1m Breakout + Failure Reversal (1m Execution)',
              variant: 'S6-F',
              tf: '1m',
            },
            {
              trackKey: 'S6F_T4',
              title: 'Track D: S6-F / T4',
              subtitle: '5m Context + 5m Breakout + Failure Reversal (5m Execution)',
              variant: 'S6-F',
              tf: '5m',
            },
          ].map((t) => {
            const m = getTrackMetrics(t.trackKey);
            const isRun = m !== null && typeof m.total_trades === 'number';
            const nTrades = typeof m?.total_trades === 'number' ? m.total_trades : null;
            const winRate = typeof m?.win_rate === 'number' ? m.win_rate : null;
            const netExpR = typeof m?.net_expectancy_R === 'number' ? m.net_expectancy_R : null;
            const grossExpR = typeof m?.gross_expectancy_R === 'number' ? m.gross_expectancy_R : null;
            const pf = typeof m?.profit_factor === 'number' ? m.profit_factor : null;
            // Verdict must come from the registered payload — never inferred.
            const g0Verdict = isRun ? m?.gate_g0_verdict ?? null : null;
            const resultInstrument = isRun && typeof m?.instrument === 'string' ? m.instrument : null;

            return (
              <div
                key={t.trackKey}
                className="p-3.5 bg-surface-subtle border border-border rounded-lg flex flex-col justify-between gap-3 hover:border-border-strong transition"
              >
                <div>
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <div className="flex items-center gap-1.5">
                      <span className="font-semibold text-ink text-xs">{t.title}</span>
                      <span className={`badge text-[10px] font-mono px-1.5 py-0.5 rounded ${t.variant === 'S6-A' ? 'bg-accent-wash text-accent-strong border border-accent-line' : 'bg-warn-wash text-warn-strong border border-warn-line'}`}>
                        {t.variant}
                      </span>
                      <span className="badge bg-inset text-ink text-[10px] font-mono px-1.5 py-0.5 rounded border border-border">
                        {t.tf}
                      </span>
                      {resultInstrument ? (
                        <span
                          className="badge bg-inset text-ink-2 text-[10px] font-mono px-1.5 py-0.5 rounded border border-border"
                          title="Instrument this registered result belongs to"
                        >
                          {resultInstrument}
                        </span>
                      ) : null}
                    </div>
                    {isRun ? (
                      g0Verdict === 'PASSED' ? (
                        <span className="badge bg-up-wash text-up-strong border border-up-line px-2 py-0.5 rounded text-[11px] font-sans inline-flex items-center gap-1">
                          <CheckCircle2 size={11} /> PASSED
                        </span>
                      ) : g0Verdict === 'INCONCLUSIVE' ? (
                        <span className="badge bg-warn-wash text-warn-strong border border-warn-line px-2 py-0.5 rounded text-[11px] font-sans inline-flex items-center gap-1" title="Sample underpowered (< 25 trades)">
                          <AlertCircle size={11} /> INCONCLUSIVE
                        </span>
                      ) : g0Verdict === 'FAILED' ? (
                        <span className="badge bg-down-wash text-down-strong border border-down-line px-2 py-0.5 rounded text-[11px] font-sans inline-flex items-center gap-1">
                          <XCircle size={11} /> FAILED
                        </span>
                      ) : (
                        <span
                          className="badge bg-inset text-ink-2 border border-border px-2 py-0.5 rounded text-[11px] font-sans inline-flex items-center gap-1"
                          title="Metrics present but the payload carried no gate verdict — not inferred."
                        >
                          <AlertCircle size={11} /> UNVERIFIED
                        </span>
                      )
                    ) : (
                      <span className="badge bg-inset text-ink-2 border border-border px-2 py-0.5 rounded text-[11px] font-sans">
                        NOT RUN
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-ink-2">{t.subtitle}</p>

                  {/* Funnel conversion badges */}
                  <div className="flex flex-wrap items-center gap-1.5 my-2.5 text-[10px] font-mono">
                    <span className="bg-surface px-1.5 py-0.5 rounded border border-border text-ink-2" title="5m Compression Episodes">
                      Episodes: <b className="text-ink">{isRun && typeof m?.compression_episodes === 'number' ? m.compression_episodes : '—'}</b>
                    </span>
                    <span className="text-ink-muted">→</span>
                    <span className="bg-surface px-1.5 py-0.5 rounded border border-border text-ink-2" title="Raw Breakouts Detected">
                      Breakouts: <b className="text-ink">{isRun && typeof m?.raw_breakouts === 'number' ? m.raw_breakouts : '—'}</b>
                    </span>
                    {t.variant === 'S6-F' && (
                      <>
                        <span className="text-ink-muted">→</span>
                        <span className="bg-surface px-1.5 py-0.5 rounded border border-border text-ink-2" title="Breakout Failures">
                          Failures: <b className="text-ink">{isRun && typeof m?.failures === 'number' ? m.failures : '—'}</b>
                        </span>
                      </>
                    )}
                    <span className="text-ink-muted">→</span>
                    <span className="bg-surface px-1.5 py-0.5 rounded border border-border text-ink-2" title="Gated Entry Candidates">
                      Candidates: <b className="text-ink">{isRun && typeof m?.total_candidates === 'number' ? m.total_candidates : '—'}</b>
                    </span>
                    <span className="text-ink-muted">→</span>
                    <span className="bg-surface px-1.5 py-0.5 rounded border border-border text-ink-2" title="Executed Fills">
                      Trades: <b className="text-ink font-bold">{isRun && nTrades !== null ? nTrades : '—'}</b>
                    </span>
                  </div>
                </div>

                {/* Performance Grid */}
                <div className="grid grid-cols-4 gap-2 pt-2 border-t border-border text-[11px] font-mono">
                  <div>
                    <span className="text-ink-2 block text-[10px]">Win Rate</span>
                    <span className="font-semibold text-ink">
                      {winRate !== null ? `${(winRate * 100).toFixed(1)}%` : '—'}
                    </span>
                  </div>
                  <div>
                    <span className="text-ink-2 block text-[10px]">Net Exp (R)</span>
                    <span className={`font-bold ${netExpR === null ? 'text-ink' : netExpR > 0 ? 'text-up-strong' : netExpR < 0 ? 'text-down-strong' : 'text-ink'}`}>
                      {netExpR !== null ? `${netExpR >= 0 ? '+' : ''}${netExpR.toFixed(3)}R` : '—'}
                    </span>
                  </div>
                  <div>
                    <span className="text-ink-2 block text-[10px]">Gross (R)</span>
                    <span className="text-ink">
                      {grossExpR !== null ? `${grossExpR >= 0 ? '+' : ''}${grossExpR.toFixed(3)}R` : '—'}
                    </span>
                  </div>
                  <div>
                    <span className="text-ink-2 block text-[10px]">Profit Factor</span>
                    <span className="text-ink">
                      {pf !== null ? pf.toFixed(2) : '—'}
                    </span>
                  </div>
                </div>

                {isRun && nTrades !== null && nTrades > 0 && nTrades < 25 && (
                  <div className="text-[10px] text-warn-strong flex items-center gap-1 font-sans">
                    <AlertCircle size={11} className="shrink-0" />
                    <span>Sample underpowered: {nTrades} trades (&lt; 25 threshold for statistical validity). Baseline inconclusive.</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* S6 Trial Registry Drawer */}
        <div className="pt-2 border-t border-border flex flex-col gap-2">
          <button
            type="button"
            className="flex items-center justify-between text-xs text-ink-2 hover:text-ink transition py-1 text-left"
            onClick={() => setShowS6Trials(!showS6Trials)}
          >
            <span className="flex items-center gap-1.5 font-medium">
              <Database size={13} className="text-accent" />
              S6 Trial Registry &amp; Audit Trail ({s6Trials.length} Registered Runs)
            </span>
            <span className="flex items-center gap-1 text-[11px] font-mono text-ink-muted">
              {showS6Trials ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </span>
          </button>

          {showS6Trials && (
            <div className="overflow-x-auto mt-1">
              {loadingS6Trials ? (
                <div className="p-3 text-xs text-ink-2 flex items-center gap-2">
                  <Loader2 size={13} className="animate-spin" />
                  Loading audit trail…
                </div>
              ) : s6Trials.length === 0 ? (
                <div className="p-3 text-xs text-ink-2">No registered trials found in local ledger.</div>
              ) : (
                <table className="w-full text-xs text-left border-collapse border border-border font-mono">
                  <thead>
                    <tr className="bg-surface-subtle text-ink-2 border-b border-border text-[11px]">
                      <th className="p-2">Trial ID</th>
                      <th className="p-2">Track</th>
                      <th className="p-2">Instrument</th>
                      <th className="p-2">Variant</th>
                      <th className="p-2">Param Hash</th>
                      <th className="p-2">Dataset Hash</th>
                      <th className="p-2">Registered At</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border text-[11px]">
                    {s6Trials.map((t) => (
                      <tr key={t.trial_id} className="hover:bg-hover">
                        <td className="p-2 text-ink font-semibold">{t.trial_id}</td>
                        <td className="p-2 text-accent font-semibold">{t.track}</td>
                        <td className="p-2 text-ink">{t.instrument}</td>
                        <td className="p-2">
                          <span className={`badge text-[10px] px-1 py-0.5 rounded ${t.variant === 'S6-A' ? 'bg-accent-wash text-accent-strong' : 'bg-warn-wash text-warn-strong'}`}>
                            {t.variant}
                          </span>
                        </td>
                        <td className="p-2 text-ink-muted">{t.parameter_hash}</td>
                        <td className="p-2 text-ink-muted">{t.dataset_hash}</td>
                        <td className="p-2 text-ink-2">
                          {t.registered_at ? new Date(t.registered_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false }) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
      </section>

      {/* Gate G1 Blocked / Research State Card */}
      {isG1Blocked && !g1Report && (
        <section className="card p-4 bg-surface border border-down-line/50 rounded-lg shadow-sm">
          <div className="flex items-start gap-3">
            <Lock className="size-5 text-down-strong shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-xs font-bold tracking-wider uppercase text-ink">
                  Gate G1: Orthogonal ML Ensemble
                </h3>
                <span className="badge bg-down-wash text-down-strong border border-down-line px-2 py-0.5 rounded text-xs font-semibold">
                  BLOCKED (Baseline Not Qualified)
                </span>
                <span className="badge bg-inset text-ink border border-border px-2 py-0.5 rounded text-xs font-mono">
                  EXPLORATORY STUDY PERMITTED
                </span>
              </div>
              <p className="text-xs text-ink-2 mt-1 leading-relaxed">
                <span>Machine Learning gate cannot be evaluated or promoted on negative baseline expectancy.</span>{' '}
                <span>Offline exploratory WFO ablation may be executed above to study feature interactions and non-linear residual structure (strictly non-promotable).</span>
              </p>
            </div>
          </div>
        </section>
      )}

      {/* Gate G1 Ablation Report Section */}
      {g1Error && (
        <div className="p-3 bg-down-wash border border-down-line rounded text-down-strong text-xs flex items-center gap-2">
          <ShieldAlert size={14} />
          {g1Error}
        </div>
      )}

      {g1Report && (
        <section className="card p-4 bg-surface border border-border rounded-lg">
          {isG1Blocked && (
            <div className="p-2.5 mb-3 bg-warn-wash border border-warn-line rounded text-xs text-warn-strong flex items-center gap-2 font-medium">
              <AlertCircle size={14} className="shrink-0" />
              <span>
                <strong>EXPLORATORY RESEARCH STUDY:</strong> Results are strictly non-promotable because foundational G0 edge is unvalidated.
              </span>
            </div>
          )}

          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-ink">
                Gate G1: Orthogonal ML Ablation (5 Arms across {g1Report.n_folds} Purged Folds)
              </h3>
              {g1Report.gate_g1_verdict === 'PASSED' ? (
                <span className="badge bg-up-wash text-up-strong border border-up-line px-2 py-0.5 rounded text-xs flex items-center gap-1">
                  <CheckCircle2 size={12} /> PASSED
                </span>
              ) : g1Report.gate_g1_verdict === 'INCONCLUSIVE' ? (
                <span className="badge bg-warn-wash text-warn-strong border border-warn-line px-2 py-0.5 rounded text-xs flex items-center gap-1">
                  <AlertCircle size={12} /> INCONCLUSIVE
                </span>
              ) : (
                <span className="badge bg-down-wash text-down-strong border border-down-line px-2 py-0.5 rounded text-xs flex items-center gap-1">
                  <XCircle size={12} /> FAILED
                </span>
              )}
            </div>
            <span className="text-xs text-ink-2">
              Correlation (A vs B): <b>{g1Report.model_correlation.toFixed(4)}</b> (Target &lt; 0.85)
            </span>
          </div>

          <div className="overflow-x-auto mb-4">
            <table className="w-full text-xs text-left border-collapse border border-border">
              <thead>
                <tr className="bg-surface-subtle text-ink-2 border-b border-border">
                  <th className="p-2.5">Ablation Arm</th>
                  <th className="p-2.5 text-right">Trades</th>
                  <th className="p-2.5 text-right">Win %</th>
                  <th className="p-2.5 text-right">Gross Exp %</th>
                  <th className="p-2.5 text-right">Net Exp %</th>
                  <th className="p-2.5 text-right">Profit Factor</th>
                  <th className="p-2.5 text-right">Max DD %</th>
                  <th className="p-2.5 text-right">Deflated Sharpe</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border font-mono">
                {Object.entries(g1Report.arms).map(([key, arm]) => (
                  <tr
                    key={key}
                    className={
                      arm.arm_name.includes('Ensemble')
                        ? 'bg-accent-wash font-semibold text-accent'
                        : 'hover:bg-hover text-ink-2'
                    }
                  >
                    <td className="p-2.5 font-sans">{arm.arm_name}</td>
                    <td className="p-2.5 text-right">{arm.total_trades}</td>
                    <td className="p-2.5 text-right">{(arm.win_rate * 100).toFixed(1)}%</td>
                    <td className="p-2.5 text-right">{(arm.gross_expectancy_pct * 100).toFixed(3)}%</td>
                    <td className={`p-2.5 text-right ${arm.net_expectancy_pct > 0 ? 'text-up-strong' : 'text-down-strong'}`}>
                      {(arm.net_expectancy_pct * 100).toFixed(3)}%
                    </td>
                    <td className="p-2.5 text-right">{arm.profit_factor.toFixed(2)}</td>
                    <td className="p-2.5 text-right">{(arm.max_drawdown_pct * 100).toFixed(1)}%</td>
                    <td className="p-2.5 text-right">{arm.deflated_sharpe_ratio.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 p-3 bg-surface-subtle rounded border border-border text-xs">
            <div>
              <span className="text-ink-2">Mean OOS Disagreement:</span>{' '}
              <b className="text-ink font-mono">{(g1Report.mean_disagreement * 100).toFixed(1)}%</b>
            </div>
            <div>
              <span className="text-ink-2">Disagreement Rejections:</span>{' '}
              <b className="text-ink font-mono">
                {g1Report.disagreement_rejections} ({g1Report.disagreement_rejection_pct.toFixed(1)}%)
              </b>
            </div>
            <div>
              <span className="text-ink-2">Inductive Orthogonality:</span>{' '}
              <b className={g1Report.model_correlation <= 0.01 ? 'text-up-strong' : 'text-warn-strong'}>
                {g1Report.model_correlation <= 0.01 ? 'PROVEN' : 'NOT PROVEN'} (Corr{' '}
                {g1Report.model_correlation.toFixed(4)})
              </b>
            </div>
          </div>
        </section>
      )}

      {g2Error && (
        <div className="p-3 bg-down-wash border border-down-line rounded text-down-strong text-xs flex items-center gap-2">
          <ShieldAlert size={14} />
          {g2Error}
        </div>
      )}

      {exportError && (
        <div className="p-3 bg-down-wash border border-down-line rounded text-down-strong text-xs flex items-center gap-2">
          <ShieldAlert size={14} />
          {exportError}
        </div>
      )}

      {g2Report && (
        <section className="card p-4 bg-surface border border-border rounded-lg">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            <div className="flex items-center gap-2">
              <Shield size={16} className="text-accent" />
              <h3 className="text-sm font-semibold text-ink">
                Gate G2: Robustness &amp; Cost-Survival ({g2Report.strategy_key})
              </h3>
              {g2Report.gate_g2_verdict === 'PASSED' ? (
                <span className="badge bg-up-wash text-up-strong border border-up-line px-2 py-0.5 rounded text-xs flex items-center gap-1">
                  <CheckCircle2 size={12} /> PASSED
                </span>
              ) : g2Report.gate_g2_verdict === 'INCONCLUSIVE' ? (
                <span className="badge bg-warn-wash text-warn-strong border border-warn-line px-2 py-0.5 rounded text-xs flex items-center gap-1">
                  <AlertCircle size={12} /> INCONCLUSIVE
                </span>
              ) : (
                <span className="badge bg-down-wash text-down-strong border border-down-line px-2 py-0.5 rounded text-xs flex items-center gap-1">
                  <XCircle size={12} /> FAILED
                </span>
              )}
            </div>
            <span className="text-xs text-ink-2 font-mono">
              Survival: <b>{g2Report.cost_survival_max_multiplier.toFixed(2)}x</b>
              {' '}· DSR: <b>{g2Report.deflated_sharpe_ratio.toFixed(2)}</b>
              {' '}· Sensitivity: <b>{g2Report.sensitivity_pass_count}/{g2Report.sensitivity_total}</b>
            </span>
          </div>

          <div className="overflow-x-auto mb-3">
            <table className="w-full text-xs text-left border-collapse border border-border">
              <thead>
                <tr className="bg-surface-subtle text-ink-2 border-b border-border">
                  <th className="p-2.5">Cost Stress</th>
                  <th className="p-2.5 text-right">Trades</th>
                  <th className="p-2.5 text-right">Net Exp %</th>
                  <th className="p-2.5 text-right">Profit Factor</th>
                  <th className="p-2.5 text-right">Max DD %</th>
                  <th className="p-2.5 text-center">Survives</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border font-mono">
                {g2Report.stress_curve.map((p) => (
                  <tr key={p.stress_multiplier} className="hover:bg-hover text-ink-2">
                    <td className="p-2.5 font-sans text-ink">{p.stress_multiplier.toFixed(2)}x</td>
                    <td className="p-2.5 text-right">{p.total_trades}</td>
                    <td className={`p-2.5 text-right ${p.net_expectancy_pct > 0 ? 'text-up-strong' : 'text-down-strong'}`}>
                      {(p.net_expectancy_pct * 100).toFixed(3)}%
                    </td>
                    <td className="p-2.5 text-right">{p.profit_factor.toFixed(2)}</td>
                    <td className="p-2.5 text-right">{(p.max_drawdown_pct * 100).toFixed(1)}%</td>
                    <td className="p-2.5 text-center">
                      {p.survives ? (
                        <span className="badge bg-up-wash text-up-strong border border-up-line px-2 py-0.5 rounded text-xs font-sans">YES</span>
                      ) : (
                        <span className="badge bg-down-wash text-down-strong border border-down-line px-2 py-0.5 rounded text-xs font-sans">NO</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="overflow-x-auto mb-3">
            <table className="w-full text-xs text-left border-collapse border border-border">
              <thead>
                <tr className="bg-surface-subtle text-ink-2 border-b border-border">
                  <th className="p-2.5">Sensitivity (k_tp / k_sl)</th>
                  <th className="p-2.5 text-right">Trades</th>
                  <th className="p-2.5 text-right">Net Exp %</th>
                  <th className="p-2.5 text-center">Positive</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border font-mono">
                {g2Report.sensitivity.map((s) => (
                  <tr key={`${s.k_tp}-${s.k_sl}`} className="hover:bg-hover text-ink-2">
                    <td className="p-2.5 font-sans text-ink">{s.k_tp.toFixed(2)} / {s.k_sl.toFixed(2)}</td>
                    <td className="p-2.5 text-right">{s.total_trades}</td>
                    <td className={`p-2.5 text-right ${s.net_expectancy_pct > 0 ? 'text-up-strong' : 'text-down-strong'}`}>
                      {(s.net_expectancy_pct * 100).toFixed(3)}%
                    </td>
                    <td className="p-2.5 text-center">
                      {s.positive ? (
                        <span className="badge bg-up-wash text-up-strong border border-up-line px-2 py-0.5 rounded text-xs font-sans">YES</span>
                      ) : (
                        <span className="badge bg-down-wash text-down-strong border border-down-line px-2 py-0.5 rounded text-xs font-sans">NO</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="p-3 bg-surface-subtle rounded border border-border text-xs">
            <div className="font-semibold text-ink-2 mb-1">Gate Evaluation Diagnostic:</div>
            <ul className="list-disc list-inside space-y-0.5 text-ink-2">
              {g2Report.verdict_reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {/* Tier 3: Synthetic Options Simulator */}
      <section className="card p-4 bg-surface border border-border rounded-lg">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Scale size={16} className="text-accent" />
            <h3 className="text-sm font-semibold text-ink">Tier 3: Synthetic Options Execution Simulator</h3>
          </div>
          <span className="text-xs text-ink-2">Black-76 European Model + Theta Decay + Indian Statutory Fees</span>
        </div>

        <div className="flex flex-wrap items-end gap-3 mb-3">
          <div>
            <label className="text-xs text-ink-2 font-medium block mb-1">Execution Structure</label>
            <div className="flex items-center rounded border border-border bg-inset p-0.5">
              <button
                type="button"
                className={`px-2.5 py-1 rounded text-xs font-medium transition ${
                  spreadMode === 'naked'
                    ? 'bg-surface text-ink shadow-sm font-semibold'
                    : 'text-ink-2 hover:text-ink'
                }`}
                onClick={() => setSpreadMode('naked')}
              >
                Naked Option
              </button>
              <button
                type="button"
                className={`px-2.5 py-1 rounded text-xs font-medium transition ${
                  spreadMode === 'spread'
                    ? 'bg-surface text-accent shadow-sm font-semibold'
                    : 'text-ink-2 hover:text-ink'
                }`}
                onClick={() => setSpreadMode('spread')}
              >
                Vertical Spread (Defined Risk)
              </button>
            </div>
          </div>

          <div>
            <label className="text-xs text-ink-2 font-medium block mb-1">Spot entry (required)</label>
            <input
              type="number"
              className="input w-32 font-mono"
              value={simSpotEntry}
              placeholder="e.g. 80000"
              onChange={(e) => setSimSpotEntry(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs text-ink-2 font-medium block mb-1">IV % (required)</label>
            <input
              type="number"
              className="input w-24 font-mono"
              value={simIvPct}
              placeholder="e.g. 14"
              onChange={(e) => setSimIvPct(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs text-ink-2 font-medium block mb-1">Strike width (required)</label>
            <input
              type="number"
              className="input w-28 font-mono"
              value={simStrikeWidth}
              placeholder="e.g. 300"
              onChange={(e) => setSimStrikeWidth(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs text-ink-2 font-medium block mb-1">DTE days (required)</label>
            <input
              type="number"
              className="input w-24 font-mono"
              value={simDte}
              placeholder="e.g. 4"
              onChange={(e) => setSimDte(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs text-ink-2 font-medium block mb-1">Holding bars (required)</label>
            <input
              type="number"
              className="input w-28 font-mono"
              value={simHoldingBars}
              placeholder="e.g. 6"
              onChange={(e) => setSimHoldingBars(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs text-ink-2 font-medium block mb-1">Bar minutes (required)</label>
            <input
              type="number"
              className="input w-28 font-mono"
              value={simBarMinutes}
              placeholder="e.g. 15"
              onChange={(e) => setSimBarMinutes(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs text-ink-2 font-medium block mb-1">Spot move pts (required)</label>
            <input
              type="number"
              className="input w-32 font-mono"
              value={simSpotMove}
              placeholder="e.g. 300"
              onChange={(e) => setSimSpotMove(e.target.value)}
            />
          </div>

          <label className="flex items-center gap-1.5 cursor-pointer text-xs text-ink font-medium select-none pb-1.5">
            <input
              type="checkbox"
              className="checkbox checkbox-sm accent-accent"
              checked={simDemo}
              onChange={(e) => toggleSimDemo(e.target.checked)}
            />
            <span>Demo inputs</span>
            <span className="badge bg-warn-wash text-warn-strong border border-warn-line px-1.5 py-0.5 rounded text-[10px] font-sans font-medium">
              EXAMPLE VALUES
            </span>
          </label>

          <button
            type="button"
            className="btn flex items-center gap-1.5 px-3 py-1.5 text-accent text-xs transition"
            disabled={optionsLoading}
            onClick={handleSimulateOptions}
          >
            <Sparkles size={13} />
            {optionsLoading ? 'Simulating…' : spreadMode === 'spread' ? 'Simulate Vertical Spread Payoff' : 'Simulate Options Payoff'}
          </button>
        </div>

        <p className="text-xs text-ink-2 mb-3">
          No spot, IV, width or DTE defaults are assumed. Fill every field, or tick &ldquo;Demo inputs&rdquo; to load
          clearly-labelled example values (80,000 spot / 14% IV / 300 width) for illustration only.
        </p>

        {simError && (
          <div className="p-3 mb-3 bg-down-wash border border-down-line rounded text-down-strong text-xs flex items-center gap-2">
            <ShieldAlert size={14} />
            {simError}
          </div>
        )}

        {simSubmitted && (
          <p
            className={`text-xs font-mono mb-3 ${simSubmitted.demo ? 'text-warn-strong' : 'text-ink-2'}`}
          >
            {simSubmitted.demo ? 'DEMO INPUTS (example, not live market data) — ' : 'Inputs at submit — '}
            spot {safeNum(simSubmitted.spotEntry, '—', 0)} · move{' '}
            {simSubmitted.move >= 0 ? '+' : ''}
            {safeNum(simSubmitted.move, '—', 0)} pts · IV {safeNum(simSubmitted.ivPct, '—', 2)}% · width{' '}
            {safeNum(simSubmitted.strikeWidth, '—', 0)} · DTE {safeNum(simSubmitted.dte, '—', 1)}d ·{' '}
            {safeNum(simSubmitted.holdingBars, '—', 0)} × {safeNum(simSubmitted.barMinutes, '—', 0)}m bars.
          </p>
        )}

        {spreadMode === 'naked' && optionsResult && (
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 p-3 bg-surface-subtle rounded border border-border text-xs font-mono">
            <div>
              <span className="text-ink-2">Strike / Type</span>
              <div className="text-sm font-bold text-ink mt-0.5">
                {optionsResult.strike} {optionsResult.option_type}
              </div>
            </div>
            <div>
              <span className="text-ink-2">Entry → Exit Prem</span>
              <div className="text-sm font-bold text-ink mt-0.5">
                ₹{optionsResult.premium_entry} → ₹{optionsResult.premium_exit}
              </div>
            </div>
            <div>
              <span className="text-ink-2">Delta at Entry</span>
              <div className="text-sm font-bold text-ink mt-0.5">{optionsResult.delta_at_entry.toFixed(2)}</div>
            </div>
            <div>
              <span className="text-ink-2">Theta / Day</span>
              <div className="text-sm font-bold text-warn-strong mt-0.5">₹{optionsResult.theta_per_day.toFixed(1)}</div>
            </div>
            <div>
              <span className="text-ink-2">Total Statutory Cost</span>
              <div className="text-sm font-bold text-down-strong mt-0.5">₹{optionsResult.total_statutory_cost_rupees.toFixed(2)}</div>
            </div>
            <div>
              <span className="text-ink-2">Net Options PnL</span>
              <div className={`text-sm font-bold mt-0.5 ${optionsResult.net_pnl_rupees >= 0 ? 'text-up-strong' : 'text-down-strong'}`}>
                ₹{optionsResult.net_pnl_rupees.toFixed(2)} ({optionsResult.options_net_roi_pct.toFixed(1)}%)
              </div>
            </div>
          </div>
        )}

        {spreadMode === 'spread' && spreadResult && (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center justify-between gap-2 p-2.5 bg-accent-wash/30 border border-accent-line rounded text-xs">
              <div className="flex items-center gap-2">
                <span className="font-bold text-ink">{spreadResult.spread_name} ({spreadResult.direction})</span>
                <span className="badge bg-up-wash text-up-strong border border-up-line px-2 py-0.5 rounded font-mono font-semibold">
                  Theta Decay Reduced: {spreadResult.theta_decay_reduction_pct.toFixed(1)}%
                </span>
              </div>
              <span className="text-ink-2 font-mono">
                Long: {spreadResult.legs.long_leg.strike} {spreadResult.legs.long_leg.option_type} | Short: {spreadResult.legs.short_leg.strike} {spreadResult.legs.short_leg.option_type}
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 p-3 bg-surface-subtle rounded border border-border text-xs font-mono">
              <div>
                <span className="text-ink-2">Net Debit Entry</span>
                <div className="text-sm font-bold text-ink mt-0.5">
                  ₹{spreadResult.net_entry.toFixed(2)} pts
                </div>
              </div>
              <div>
                <span className="text-ink-2">Net Exit Value</span>
                <div className="text-sm font-bold text-ink mt-0.5">
                  ₹{spreadResult.net_exit.toFixed(2)} pts
                </div>
              </div>
              <div>
                <span className="text-ink-2">Net Delta</span>
                <div className="text-sm font-bold text-ink mt-0.5">{spreadResult.net_greeks.net_delta.toFixed(3)}</div>
              </div>
              <div>
                <span className="text-ink-2">Net Theta / Day</span>
                <div className="text-sm font-bold text-warn-strong mt-0.5">
                  {spreadResult.net_greeks.net_theta_per_day.toFixed(2)} pts
                </div>
              </div>
              <div>
                <span className="text-ink-2">Statutory (4 Legs)</span>
                <div className="text-sm font-bold text-down-strong mt-0.5">₹{spreadResult.costs.total_cost.toFixed(2)}</div>
              </div>
              <div>
                <span className="text-ink-2">Net Spread PnL</span>
                <div className={`text-sm font-bold mt-0.5 ${spreadResult.net_pnl_rupees >= 0 ? 'text-up-strong' : 'text-down-strong'}`}>
                  ₹{spreadResult.net_pnl_rupees.toFixed(2)} ({spreadResult.net_roi_pct.toFixed(1)}%)
                </div>
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

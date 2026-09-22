'use client';

import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  Cpu,
  Flame,
  Gauge,
  Layers,
  RefreshCw,
  ShieldAlert,
  Zap,
} from 'lucide-react';
import { useVortexHUD } from '@/hooks/useVortexHUD';

interface VortexSnapHUDProps {
  initialSymbol?: string;
}

/**
 * Backend HUD contract extensions not yet in the shared `vortex.ts` types.
 * Kept local (this file owns them) until the shared type catches up.
 */
type VortexLevelDetail = {
  price?: number | null;
  level_type?: string | null;
  relevance?: number | null;
  relevance_score?: number | null;
  touches?: number | null;
  touch_count?: number | null;
  rejections?: number | null;
  rejection_count?: number | null;
  is_broken?: boolean | null;
  is_retest?: boolean | null;
  is_retested?: boolean | null;
  distance_points?: number | null;
};

type VortexRegimeExtended = {
  regime: string;
  confidence: number;
  adx: number;
  atr_14?: number | null;
  efficiency_ratio?: number | null;
  volatility_state?: string | null;
  is_fallback?: boolean | null;
  fallback_reason?: string | null;
};

type VortexLevelsExtended = {
  nearest_support: number | null;
  nearest_resistance: number | null;
  nearest_support_type?: string | null;
  nearest_resistance_type?: string | null;
  nearest_support_detail?: VortexLevelDetail | null;
  nearest_resistance_detail?: VortexLevelDetail | null;
  support_distance_points?: number | null;
  resistance_distance_points?: number | null;
};

type ResolvedLevel = {
  price: number | null;
  levelType: string | null;
  relevance: number | null;
  touches: number | null;
  rejections: number | null;
  isBroken: boolean;
  isRetest: boolean;
  distancePoints: number | null;
};

function formatMinutesToClose(minutes: number): string {
  if (!Number.isFinite(minutes) || minutes <= 0) return '0m to close';
  const total = Math.round(minutes);
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h <= 0) return `${m}m to close`;
  return `${h}h ${m}m to close`;
}

/** Age text for the hook's ageMs. Null when the payload carried no usable instant. */
function formatAgeMs(ms: number | null): string | null {
  if (ms === null || !Number.isFinite(ms)) return null;
  const seconds = Math.max(0, Math.round(ms / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m ago`;
}

function formatIstTime(ms: number | null): string | null {
  if (ms === null || !Number.isFinite(ms)) return null;
  return new Date(ms).toLocaleTimeString('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function fallbackReasonText(reason: string | null): string {
  if (!reason) return 'Regime call not trusted (fallback path).';
  if (reason.startsWith('ablation_or_insufficient_data')) {
    return 'Ablation disabled or insufficient history — regime returned UNKNOWN.';
  }
  if (reason === 'low_confidence_fallback') {
    return 'Confidence at or below 30% — measurement not trusted.';
  }
  return reason;
}

/** Full level detail; the bare price fallback is only shown when type is known. */
function resolveLevel(
  detail: VortexLevelDetail | null | undefined,
  fallbackPrice: number | null,
  fallbackType: string | null | undefined,
  fallbackDistance: number | null | undefined,
): ResolvedLevel {
  const rawPrice = detail?.price ?? fallbackPrice;
  const price = typeof rawPrice === 'number' && Number.isFinite(rawPrice) ? rawPrice : null;
  const rawRelevance = detail?.relevance ?? detail?.relevance_score;
  const rawTouches = detail?.touches ?? detail?.touch_count;
  const rawRejections = detail?.rejections ?? detail?.rejection_count;
  const rawDistance = detail?.distance_points ?? fallbackDistance;
  return {
    price,
    levelType: detail?.level_type ?? fallbackType ?? null,
    relevance:
      typeof rawRelevance === 'number' && Number.isFinite(rawRelevance) ? rawRelevance : null,
    touches: typeof rawTouches === 'number' && Number.isFinite(rawTouches) ? rawTouches : null,
    rejections:
      typeof rawRejections === 'number' && Number.isFinite(rawRejections) ? rawRejections : null,
    isBroken: detail?.is_broken === true,
    isRetest: detail?.is_retest === true || detail?.is_retested === true,
    distancePoints:
      typeof rawDistance === 'number' && Number.isFinite(rawDistance) ? rawDistance : null,
  };
}

function formatPercent(frac: number | null): string {
  return frac === null ? 'No data' : `${Math.round(frac * 100)}%`;
}

/** One structural level cell: price + type + relevance + touches/rejections. */
function LevelCell({ level, tone }: { level: ResolvedLevel; tone: 'support' | 'resistance' }) {
  const label = tone === 'support' ? 'Support' : 'Resistance';
  const priceClass = tone === 'support' ? 'text-up-strong' : 'text-down-strong';
  if (level.price === null) {
    return (
      <div className="p-2 rounded bg-surface-subtle border border-border">
        <span className="text-[10px] uppercase font-bold text-ink-2 block">{label}</span>
        <span className="text-ink-3 font-bold block mt-0.5">None</span>
        <span className="text-[10px] text-ink-2 block mt-1">No structural level in range.</span>
      </div>
    );
  }
  const qualifiers = [level.isBroken ? 'broken' : null, level.isRetest ? 'retested' : null]
    .filter((v): v is string => v !== null)
    .join(' · ');
  return (
    <div className="p-2 rounded bg-surface-subtle border border-border">
      <span className="text-[10px] uppercase font-bold text-ink-2 block">{label}</span>
      <span className={`${priceClass} font-bold block mt-0.5`}>{level.price.toFixed(1)}</span>
      <span className="text-[10px] text-ink-2 block">
        {level.distancePoints !== null ? `${level.distancePoints.toFixed(1)} pts away` : 'Distance: No data'}
      </span>
      <span
        className="text-[10px] text-ink-2 block mt-1"
        title="Level type, relevance and touch/rejection counts from the microstructure payload"
      >
        Type: {level.levelType ?? 'No data'}
        {qualifiers ? ` (${qualifiers})` : ''}
      </span>
      <span className="text-[10px] text-ink-2 block">
        Relevance: {formatPercent(level.relevance)} ·{' '}
        {level.touches !== null || level.rejections !== null
          ? `${level.touches ?? '—'} touches · ${level.rejections ?? '—'} rejections`
          : 'Touches/rejections: No data'}
      </span>
    </div>
  );
}

export function VortexSnapHUD({ initialSymbol = 'SENSEX' }: VortexSnapHUDProps) {
  const {
    symbol,
    setSymbol,
    hud,
    status,
    loading,
    error,
    autoRefresh,
    setAutoRefresh,
    refresh,
    ageMs,
    stale,
    live,
    lastCandleTimestampMs,
    isSimulated,
    tradingDisabled,
    dataSource,
  } = useVortexHUD({ initialSymbol });

  const regime = hud?.market_regime as VortexRegimeExtended | undefined;
  const levels = hud?.structural_levels as VortexLevelsExtended | undefined;
  const support = resolveLevel(
    levels?.nearest_support_detail,
    levels?.nearest_support ?? null,
    levels?.nearest_support_type,
    levels?.support_distance_points,
  );
  const resistance = resolveLevel(
    levels?.nearest_resistance_detail,
    levels?.nearest_resistance ?? null,
    levels?.nearest_resistance_type,
    levels?.resistance_distance_points,
  );
  const regimeFallback = regime?.is_fallback === true;
  const ageText = formatAgeMs(ageMs);
  const lastCandleText = formatIstTime(lastCandleTimestampMs);
  // No payload yet: SYNCING while the first fetch is in flight, NO DATA after
  // a failure — never STALE (that label is for an aged payload).
  const noPayload = hud === null;
  const feedLabel = isSimulated
    ? 'SIMULATED'
    : noPayload
      ? loading
        ? 'SYNCING'
        : 'NO DATA'
      : stale
        ? ageText
          ? `STALE · ${ageText}`
          : 'STALE · age unknown'
        : live
          ? 'LIVE'
          : 'NO DATA';
  const feedPillClass = isSimulated || (!noPayload && stale)
    ? 'bg-warn-wash text-warn-strong border border-warn-line'
    : live
      ? 'bg-up-wash text-up-strong border border-up-line'
      : 'bg-inset text-ink-2 border border-border';
  const tradeBlockTitle = isSimulated
    ? 'SIMULATED feed — trade actions disabled. No paper execution from simulated marks.'
    : 'Feed is not live (stale or unknown freshness) — trade actions disabled.';
  const tradeBlockNote = isSimulated
    ? 'SIMULATED feed — trade actions disabled. Levels are for research, not fills.'
    : 'Feed is not live — trade actions disabled until a fresh candle arrives.';

  return (
    <div className="flex flex-col gap-3.5 text-ink">
      {/* Top Bar: Engine Status, Symbol Selector, Controls */}
      <div className="card p-3 sm:p-4 bg-surface border border-border rounded-lg shadow-sm flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-lg bg-accent-wash border border-accent-line text-accent">
            <Zap className={`w-5 h-5 ${live ? 'animate-pulse' : ''}`} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-base tracking-tight text-ink">VORTEX-SNAP</h3>
              {live && status?.version ? (
                <span className="badge b-bull" title="Backend engine version">
                  Engine {status.version}
                </span>
              ) : null}
              <span
                className="px-2 py-0.5 text-xs font-mono font-semibold rounded bg-accent-wash text-ink border border-accent-line"
                title="Execution timeframe: 1m. Contextual regime timeframe: 5m. Not a trade-execution state."
              >
                TF: 1m exec · 5m regime
              </span>
              <span
                className={`px-2 py-0.5 text-xs font-mono font-semibold rounded ${feedPillClass}`}
                title={
                  isSimulated
                    ? dataSource?.note ?? 'Simulated feed — not live market data'
                    : stale
                      ? 'Last candle is outside the freshness window — values are last known, not live'
                      : live
                        ? 'Fresh candle within the staleness window'
                        : 'No fresh data received yet'
                }
              >
                {feedLabel}
              </span>
            </div>
            <p className="text-xs text-ink-2 mt-0.5">
              Microstructure Scalping Engine · Directional Pressure &amp; Translation Acceptance
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Symbol Switcher */}
          <span className="seg" title="Underlying index">
            {['SENSEX', 'NIFTY', 'BANKNIFTY'].map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setSymbol(s)}
                className="seg-btn"
                data-active={symbol === s}
              >
                {s}
              </button>
            ))}
          </span>

          <button
            type="button"
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`btn btn-ic text-xs ${
              autoRefresh && live
                ? 'bg-up-wash text-up-strong border-up-line hover:bg-up-wash'
                : 'text-ink-2 hover:text-ink'
            }`}
            title={
              autoRefresh
                ? live
                  ? 'Auto-refresh every 5s — feed fresh'
                  : stale
                    ? `Auto-refresh on but feed is STALE${ageText ? ` (${ageText})` : ''} — showing last known mark`
                    : 'Auto-refresh on — waiting for first data'
                : 'Auto-refresh paused'
            }
          >
            <Activity className={`w-3.5 h-3.5 ${autoRefresh && live ? 'text-up-strong' : 'text-ink-3'}`} />
            {!autoRefresh ? 'Paused' : noPayload ? (loading ? 'Loading…' : 'No data') : live ? 'Live (5s)' : stale ? 'STALE' : 'No data'}
          </button>

          <button
            type="button"
            onClick={() => void refresh()}
            disabled={loading}
            className="btn btn-ic p-1.5 text-xs text-ink-2 hover:text-ink"
            title="Refresh now"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-down-wash border border-down-line text-down-strong text-xs font-medium flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {!isSimulated && stale && hud ? (
        <div className="p-3 rounded-lg bg-warn-wash border border-warn-line text-warn-strong text-xs font-medium flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <div className="flex flex-col gap-1">
            <span className="font-semibold">
              STALE DATA — values are last known, not live
              {ageText ? ` · last candle ${ageText}` : ' · age unknown'}
            </span>
            <span>
              {lastCandleText ? `Last candle ${lastCandleText} IST. ` : ''}
              Trade actions stay disabled until the feed advances.
            </span>
          </div>
        </div>
      ) : null}

      {isSimulated && (
        <div className="p-3 rounded-lg bg-warn-wash border border-warn-line text-warn-strong text-xs font-medium flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <div className="flex flex-col gap-1">
            <span className="font-semibold">SIMULATED DATA — NOT LIVE MARKET — trade actions disabled</span>
            <span>{dataSource?.note ?? 'Generated at runtime; not real market data.'}</span>
            <span className="text-[10px] font-mono text-ink-3">
              Type: {dataSource?.type ?? 'unknown'} · Instrument: {dataSource?.instrument ?? symbol} · Source:{' '}
              {dataSource?.path ?? 'generated at runtime'}
            </span>
          </div>
        </div>
      )}

      {/* Session Progress & ML Telemetry Ribbon */}
      {status && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
          <div className="card p-3 bg-surface border border-border rounded-lg shadow-sm flex flex-col justify-between">
            <span className="text-[10px] uppercase font-bold text-ink-2 tracking-wider">Market Session</span>
            <div className="flex items-baseline justify-between mt-1">
              <span className="text-sm font-semibold text-ink font-mono">
                {status.session.phase}
              </span>
              <span className="text-xs text-ink-2 font-mono font-medium">
                {formatMinutesToClose(status.session.minutes_to_market_close)}
              </span>
            </div>
            <div className="w-full bg-inset rounded-full h-1.5 mt-2 overflow-hidden">
              <div
                className="bg-accent h-1.5 rounded-full transition-all duration-500"
                style={{ width: `${Math.min(100, status.session.session_progress_pct)}%` }}
              />
            </div>
          </div>

          <div className="card p-3 bg-surface border border-border rounded-lg shadow-sm flex flex-col justify-between">
            <span className="text-[10px] uppercase font-bold text-ink-2 tracking-wider">ML Validator (§25)</span>
            <div className="flex items-center gap-2 mt-1">
              <Cpu className="w-4 h-4 text-accent" />
              <span className="text-sm font-semibold text-ink font-mono">
                {status.ml_validator.is_model_loaded ? 'Trained LightGBM' : 'Heuristic Mode'}
              </span>
            </div>
            <span className="text-[11px] text-ink-2 mt-1">
              22 Features · Platt Calibrated (p &ge; {status.ml_validator.acceptance_threshold})
            </span>
          </div>

          <div className="card p-3 bg-surface border border-border rounded-lg shadow-sm flex flex-col justify-between">
            <span className="text-[10px] uppercase font-bold text-ink-2 tracking-wider">Trading Eligibility</span>
            <div className="flex items-center gap-2 mt-1">
              {status.session.is_trading_allowed ? (
                <>
                  <CheckCircle2 className="w-4 h-4 text-up-strong" />
                  <span className="text-sm font-semibold text-up-strong">Trading Window Open</span>
                </>
              ) : (
                <>
                  <ShieldAlert className="w-4 h-4 text-warn-strong" />
                  <span className="text-sm font-semibold text-warn-strong">
                    {status.session.is_forced_square_off ? 'Forced Square-Off' : 'Window Closed'}
                  </span>
                </>
              )}
            </div>
            <span className="text-[11px] text-ink-2 mt-1">
              Forced Square-off strictly at 15:15 IST
            </span>
          </div>

          <div className="card p-3 bg-surface border border-border rounded-lg shadow-sm flex flex-col justify-between">
            <div className="flex items-center justify-between gap-1.5">
              <span className="text-[10px] uppercase font-bold text-ink-2 tracking-wider">Primary Hypothesis</span>
              <span
                className="text-[9px] uppercase font-bold tracking-wider rounded border border-warn-line bg-warn-wash px-1.5 py-0.5 text-warn-strong"
                title="Backtest result from historical SENSEX data — not a live verified edge"
              >
                Research claim (backtest)
              </span>
            </div>
            <span
              className="text-xs text-ink-2 font-medium mt-1 leading-tight"
              title={
                symbol === 'SENSEX'
                  ? 'SENSEX backtest reference (research claim — not a live verified edge)'
                  : `Research claim from SENSEX backtests — unverified for ${symbol}`
              }
            >
              {symbol === 'SENSEX'
                ? 'Translation Ratio alpha — SENSEX backtest dSharpe +0.89. Not live-verified.'
                : `Not verified for ${symbol}. SENSEX backtest dSharpe +0.89 is a research reference only.`}
            </span>
            <span className="text-[11px] text-ink-2 mt-1">
              Zero Magic Numbers · Fully Parametrized
            </span>
          </div>
        </div>
      )}

      {/* Main Microstructure Gauge Grid */}
      {hud && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {/* Card 1: Compression Zone */}
          <div className="card p-3.5 bg-surface border border-border rounded-lg shadow-sm hover:border-border-strong transition flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-ink-2 flex items-center gap-1.5">
                <Layers className="w-4 h-4 text-accent" />
                Compression Engine (§6)
              </span>
              <span
                className={`px-2 py-0.5 rounded text-xs font-mono font-bold ${
                  hud.compression.zone === 'EXTREME'
                    ? 'bg-accent-wash text-accent border border-accent-line'
                    : hud.compression.zone === 'ARMED'
                    ? 'bg-warn-wash text-warn-strong border border-warn-line'
                    : 'bg-inset text-ink-2 border border-border'
                }`}
              >
                {hud.compression.zone}
              </span>
            </div>

            <div className="mt-3 flex items-baseline justify-between">
              <span className="text-2xl font-bold font-mono text-ink tracking-tight">
                {(hud.compression.score * 100).toFixed(1)}%
              </span>
              <span className="text-xs font-mono text-ink-2">
                Duration: <strong className="text-ink">{hud.compression.duration_bars} bars</strong>
              </span>
            </div>

            <div className="w-full bg-inset rounded-full h-2 mt-2 overflow-hidden">
              <div
                className={`h-2 rounded-full transition-all duration-300 ${
                  hud.compression.score >= 0.8
                    ? 'bg-accent'
                    : hud.compression.score >= 0.6
                    ? 'bg-accent/80'
                    : 'bg-border-strong'
                }`}
                style={{ width: `${hud.compression.score * 100}%` }}
              />
            </div>

            <div className="mt-3 pt-2 border-t border-border-subtle flex justify-between text-xs text-ink-2">
              <span>Channel Contraction:</span>
              <span className="font-mono text-ink font-semibold">{hud.compression.channel_range_pct}%</span>
            </div>
          </div>

          {/* Card 2: Directional Pressure */}
          <div className="card p-3.5 bg-surface border border-border rounded-lg shadow-sm hover:border-border-strong transition flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-ink-2 flex items-center gap-1.5">
                <Gauge className="w-4 h-4 text-accent" />
                Directional Pressure (§7)
              </span>
              <span
                className={`px-2 py-0.5 rounded text-xs font-mono font-bold flex items-center gap-1 ${
                  hud.directional_pressure.is_bullish
                    ? 'bg-up-wash text-up-strong border border-up-line'
                    : 'bg-down-wash text-down-strong border border-down-line'
                }`}
              >
                {hud.directional_pressure.is_bullish ? (
                  <>
                    <ArrowUpRight className="w-3.5 h-3.5" /> BULLISH
                  </>
                ) : (
                  <>
                    <ArrowDownRight className="w-3.5 h-3.5" /> BEARISH
                  </>
                )}
              </span>
            </div>

            <div className="mt-3 flex items-baseline justify-between">
              <span
                className={`text-2xl font-bold font-mono tracking-tight ${
                  hud.directional_pressure.score >= 0 ? 'text-up-strong' : 'text-down-strong'
                }`}
              >
                {hud.directional_pressure.score > 0 ? '+' : ''}
                {hud.directional_pressure.score.toFixed(3)}
              </span>
              <span className="text-xs font-mono text-ink-2">
                Persistence:{' '}
                <strong className="text-ink">
                  {hud.directional_pressure.persistence_abs ?? Math.abs(hud.directional_pressure.persistence)} bars
                </strong>
              </span>
            </div>

            {/* Bipolar Pressure Bar (-1.0 to +1.0) */}
            <div className="w-full bg-inset rounded-full h-2 mt-2 relative overflow-hidden">
              <div
                className={`h-2 transition-all duration-300 ${
                  hud.directional_pressure.score >= 0 ? 'bg-up-strong' : 'bg-down-strong'
                }`}
                style={{
                  width: `${Math.abs(hud.directional_pressure.score) * 50}%`,
                  marginLeft:
                    hud.directional_pressure.score >= 0
                      ? '50%'
                      : `${50 - Math.abs(hud.directional_pressure.score) * 50}%`,
                }}
              />
            </div>

            <div
              className="mt-3 pt-2 border-t border-border-subtle flex justify-between text-xs text-ink-2"
              title={
                hud.directional_pressure.acceleration_raw !== undefined
                  ? `Raw: ${hud.directional_pressure.acceleration_raw}/bar² (volume units). Normalized by pressure scale.`
                  : 'Scale-normalized acceleration (score units / bar)'
              }
            >
              <span>Pressure Acceleration (norm):</span>
              <span className="font-mono text-ink font-semibold">
                {hud.directional_pressure.acceleration > 0 ? '+' : ''}
                {hud.directional_pressure.acceleration.toFixed(4)}/bar
              </span>
            </div>
          </div>

          {/* Card 3: Translation Ratio (Primary Hypothesis) */}
          <div className="card p-3.5 bg-surface border border-border rounded-lg shadow-sm hover:border-border-strong transition flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-ink-2 flex items-center gap-1.5">
                <Flame className="w-4 h-4 text-warn-strong" />
                Translation Ratio (§8)
              </span>
              <span
                className={`px-2 py-0.5 rounded text-[11px] font-mono font-bold ${
                  hud.translation_ratio.is_directional_acceptance
                    ? 'bg-up-wash text-up-strong border border-up-line'
                    : hud.translation_ratio.is_absorption_candidate
                    ? 'bg-accent-wash text-accent border border-accent-line'
                    : hud.translation_ratio.is_rejection_conflict
                    ? 'bg-down-wash text-down-strong border border-down-line'
                    : 'bg-inset text-ink-2 border border-border'
                }`}
              >
                {hud.translation_ratio.is_directional_acceptance
                  ? 'ACCEPTANCE'
                  : hud.translation_ratio.is_absorption_candidate
                    ? 'ABSORPTION'
                    : hud.translation_ratio.is_rejection_conflict
                      ? 'CONFLICT'
                      : 'NEUTRAL'}
              </span>
            </div>

            <div className="mt-3 flex items-baseline justify-between">
              <span className="text-2xl font-bold font-mono text-warn-strong tracking-tight">
                {hud.translation_ratio.ratio.toFixed(2)}x
              </span>
              <span
                className="text-xs font-mono text-ink-2"
                title={`Normalized displacement: ${(hud.translation_ratio.displacement_norm ?? hud.translation_ratio.displacement).toFixed(2)}x ATR`}
              >
                Displacement:{' '}
                <strong className="text-ink">
                  {(hud.translation_ratio.displacement_pts ?? hud.translation_ratio.displacement).toFixed(1)} pts
                </strong>
              </span>
            </div>

            <div className="w-full bg-inset rounded-full h-2 mt-2 overflow-hidden">
              <div
                className="bg-warn-strong h-2 rounded-full transition-all duration-300"
                style={{ width: `${Math.min(100, (hud.translation_ratio.ratio / 2.0) * 100)}%` }}
              />
            </div>

            <div className="mt-3 pt-2 border-t border-border-subtle flex justify-between text-xs text-ink-2">
              <span>Primary Alpha Signal:</span>
              <span className="font-mono text-ink font-medium">
                {hud.translation_ratio.is_directional_acceptance
                  ? 'Directional Flow Confirmed'
                  : hud.translation_ratio.is_absorption_candidate
                    ? 'Absorption Suspected'
                    : hud.translation_ratio.is_rejection_conflict
                      ? 'Monitoring Rejection Barrier'
                      : 'Awaiting Pressure Build'}
              </span>
            </div>
          </div>

          {/* Card 4: Absorption & Liquidity Vacuum */}
          <div className="card p-3.5 bg-surface border border-border rounded-lg shadow-sm hover:border-border-strong transition flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-ink-2 flex items-center gap-1.5">
                <Activity className="w-4 h-4 text-accent" />
                Absorption &amp; Vacuum (§9, §10)
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2.5 mt-3">
              <div className="p-2.5 rounded-md bg-surface-subtle border border-border">
                <span className="text-[10px] uppercase font-bold text-ink-2 block">Absorption</span>
                <span
                  className={`text-xs font-semibold font-mono mt-0.5 block ${
                    hud.absorption.is_detected ? 'text-ink' : 'text-ink-2'
                  }`}
                >
                  {hud.absorption.is_detected ? 'DETECTED' : 'IDLE'}
                </span>
                <span className="text-[10px] text-ink-2 mt-1 block">
                  Shock: {hud.absorption.exhaustion_volume_ratio.toFixed(1)}x
                </span>
              </div>

              <div className="p-2.5 rounded-md bg-surface-subtle border border-border">
                <span className="text-[10px] uppercase font-bold text-ink-2 block">Vacuum</span>
                <span
                  className={`text-xs font-semibold font-mono mt-0.5 block ${
                    hud.liquidity_vacuum.is_detected ? 'text-ink' : 'text-ink-2'
                  }`}
                >
                  {hud.liquidity_vacuum.is_detected ? `VACUUM (${hud.liquidity_vacuum.thin_depth_side})` : 'NORMAL'}
                </span>
                <span className="text-[10px] text-ink-2 mt-1 block">
                  Velocity: {hud.liquidity_vacuum.displacement_velocity.toFixed(1)}x
                </span>
              </div>
            </div>

            <div className="mt-3 pt-2 border-t border-border-subtle flex justify-between text-xs text-ink-2">
              <span>Vacuum Score:</span>
              <span className="font-mono text-ink font-semibold">
                {(hud.liquidity_vacuum.vacuum_score * 100).toFixed(1)}%
              </span>
            </div>
          </div>

          {/* Card 5: Snap Energy Composite */}
          <div className="card p-3.5 bg-surface border border-border rounded-lg shadow-sm hover:border-border-strong transition flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-ink-2 flex items-center gap-1.5">
                <Zap className="w-4 h-4 text-accent" />
                Snap Energy Composite (§11)
              </span>
              <span
                className={`px-2 py-0.5 rounded text-xs font-mono font-bold ${
                  hud.snap_energy.is_snap_ready
                    ? 'bg-up-wash text-up-strong border border-up-line animate-pulse'
                    : 'bg-inset text-ink-2 border border-border'
                }`}
              >
                {hud.snap_energy.is_snap_ready ? 'SNAP READY' : hud.snap_energy.energy_tier}
              </span>
            </div>

            <div className="mt-3 flex items-baseline justify-between">
              <span className="text-2xl font-bold font-mono text-ink tracking-tight">
                {(hud.snap_energy.energy_score * 100).toFixed(1)}%
              </span>
              <span className="text-xs font-mono text-ink-2">
                Release Potential: <strong className="text-ink">{hud.snap_energy.energy_tier}</strong>
              </span>
            </div>

            <div className="w-full bg-inset rounded-full h-2 mt-2 overflow-hidden">
              <div
                className="bg-accent h-2 rounded-full transition-all duration-300"
                style={{ width: `${hud.snap_energy.energy_score * 100}%` }}
              />
            </div>

            <div className="mt-3 pt-2 border-t border-border-subtle flex justify-between text-xs text-ink-2">
              <span>Ignition Requirement (rule):</span>
              <span className="font-mono text-ink font-semibold" title="Rule — snap fires only at or above 65% energy">Rule: &ge; 65% Snap Energy</span>
            </div>
          </div>

          {/* Card 6: Market Regime & Levels */}
          <div className="card p-3.5 bg-surface border border-border rounded-lg shadow-sm hover:border-border-strong transition flex flex-col justify-between">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-ink-2 flex items-center gap-1.5">
                <Layers className="w-4 h-4 text-accent" />
                Regime &amp; Context Levels (§19, §5)
              </span>
              <span
                className={`px-2 py-0.5 rounded text-xs font-mono font-bold border ${
                  regimeFallback
                    ? 'bg-warn-wash text-warn-strong border-warn-line'
                    : 'bg-inset text-ink border-border'
                }`}
                title={regimeFallback ? 'Backend flagged this regime call as a low-trust fallback' : undefined}
              >
                {regime?.regime ?? 'No data'}
                {regimeFallback ? ' · FALLBACK' : ''}
              </span>
            </div>

            {regimeFallback ? (
              <p className="mt-1.5 text-[10px] font-medium text-warn-strong leading-tight">
                Low-trust fallback — {fallbackReasonText(regime?.fallback_reason ?? null)}
              </p>
            ) : null}

            <div className="mt-3 grid grid-cols-2 gap-x-2 gap-y-1 text-xs text-ink-2">
              <span>
                Confidence:{' '}
                <strong className="text-ink font-mono">
                  {typeof regime?.confidence === 'number' ? `${(regime.confidence * 100).toFixed(0)}%` : 'No data'}
                </strong>
              </span>
              <span className="text-right">
                Trend ADX:{' '}
                <strong className="text-ink font-mono">
                  {typeof regime?.adx === 'number' ? regime.adx.toFixed(1) : 'No data'}
                </strong>
              </span>
              <span>
                ATR-14:{' '}
                <strong className="text-ink font-mono">
                  {typeof regime?.atr_14 === 'number' ? `${regime.atr_14.toFixed(2)} pts` : 'No data'}
                </strong>
              </span>
              <span className="text-right">
                Volatility:{' '}
                <strong className="text-ink font-mono">{regime?.volatility_state ?? 'No data'}</strong>
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 mt-2 text-xs font-mono">
              <LevelCell level={support} tone="support" />
              <LevelCell level={resistance} tone="resistance" />
            </div>
          </div>
        </div>
      )}

      {/* 16-State FSM Visualizer & Transition Breadcrumb (§16) */}
      {hud && (
        <div className="card p-3.5 sm:p-4 bg-surface border border-border rounded-lg shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-ink-2">
                16-State FSM State Machine (§16)
              </span>
              <span className="px-2.5 py-0.5 text-xs font-mono font-bold rounded-full bg-accent-wash text-ink border border-accent-line">
                Current State: {hud.fsm_state.current_state}
              </span>
            </div>
            <span className="text-xs text-ink-2 font-mono font-medium">
              Bars in state: {hud.fsm_state.state_enter_bar_count}
            </span>
          </div>

          {/* Transition Audit Trail */}
          <div className="flex flex-wrap items-center gap-2 p-2.5 rounded-md bg-surface-subtle border border-border">
            <span className="text-xs text-ink-2 font-medium mr-1">Lifecycle:</span>
            {hud.fsm_state.transition_history.length > 0 ? (
              hud.fsm_state.transition_history.map((t, i) => (
                <div key={i} className="flex items-center gap-1.5 text-xs font-mono">
                  <span className="px-2 py-0.5 rounded bg-surface text-ink-2 border border-border shadow-xs">
                    {t.from_state}
                  </span>
                  <span className="text-ink-4">&rarr;</span>
                  <span className="px-2 py-0.5 rounded bg-accent-wash text-accent border border-accent-line font-semibold">
                    {t.to_state}
                  </span>
                  {i < hud.fsm_state.transition_history.length - 1 && (
                    <span className="text-border-strong mx-1">|</span>
                  )}
                </div>
              ))
            ) : (
              <span className="text-xs text-ink-2 italic">
                State machine active in IDLE state awaiting compression arming.
              </span>
            )}
          </div>
        </div>
      )}

      {/* Active Signal Candidate Card or Disciplined NO-TRADE Banner */}
      {hud && (
        <div className="card p-4 bg-surface border border-border rounded-lg shadow-sm">
          {hud.active_candidate ? (
            <div>
              <div className="flex items-center justify-between pb-3 border-b border-border">
                <div className="flex items-center gap-2">
                  <span className="px-2.5 py-1 text-xs font-bold rounded bg-up-strong text-white">
                    ACTIVE CANDIDATE
                  </span>
                  <span className="text-base font-bold text-ink font-mono">
                    {hud.active_candidate.underlying} {hud.active_candidate.direction}
                  </span>
                  {isSimulated ? (
                    <span
                      className="px-2 py-0.5 text-xs font-mono font-semibold rounded bg-warn-wash text-warn-strong border border-warn-line"
                      title="SIMULATED feed — trade actions disabled"
                    >
                      SIMULATED
                    </span>
                  ) : null}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-ink-3">Confidence:</span>
                  <span className="text-sm font-mono font-bold text-accent">
                    {(hud.active_candidate.confidence * 100).toFixed(1)}%
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 my-3 font-mono">
                <div className="p-2.5 rounded-md bg-surface-subtle border border-border">
                  <span className="text-[10px] uppercase font-bold text-ink-3 block">Trigger Price</span>
                  <span className="text-base font-bold text-ink mt-0.5 block">
                    ₹{hud.active_candidate.trigger_price.toFixed(2)}
                  </span>
                </div>
                <div className="p-2.5 rounded-md bg-surface-subtle border border-border">
                  <span className="text-[10px] uppercase font-bold text-ink-3 block">Stop Loss</span>
                  <span className="text-base font-bold text-down-strong mt-0.5 block">
                    ₹{hud.active_candidate.stop_loss.toFixed(2)}
                  </span>
                </div>
                <div className="p-2.5 rounded-md bg-surface-subtle border border-border">
                  <span className="text-[10px] uppercase font-bold text-ink-3 block">Target 1 (0.8x)</span>
                  <span className="text-base font-bold text-up-strong mt-0.5 block">
                    ₹{hud.active_candidate.target_1.toFixed(2)}
                  </span>
                </div>
                <div className="p-2.5 rounded-md bg-surface-subtle border border-border">
                  <span className="text-[10px] uppercase font-bold text-ink-3 block">Target 2 (1.3x)</span>
                  <span className="text-base font-bold text-accent mt-0.5 block">
                    ₹{hud.active_candidate.target_2.toFixed(2)}
                  </span>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-1.5 mt-2">
                <span className="text-xs text-ink-3 mr-1">Reason Codes:</span>
                {hud.active_candidate.reason_codes.map((rc, idx) => (
                  <span
                    key={idx}
                    className="px-2 py-0.5 text-[11px] font-mono rounded bg-inset text-ink-2 border border-border"
                  >
                    {rc}
                  </span>
                ))}
              </div>

              <div className="mt-3">
                <button
                  type="button"
                  disabled={tradingDisabled}
                  title={tradingDisabled ? tradeBlockTitle : 'Execute candidate as a paper order'}
                  className="btn w-full disabled:opacity-50"
                >
                  {tradingDisabled
                    ? isSimulated
                      ? 'Trade actions disabled — SIMULATED'
                      : 'Trade actions disabled — NOT LIVE'
                    : 'Execute candidate (paper)'}
                </button>
                {tradingDisabled ? (
                  <p className="mt-1 text-[11px] text-warn-strong">{tradeBlockNote}</p>
                ) : null}
              </div>
            </div>
          ) : (
            <div className="flex items-start gap-3 py-1 text-ink-2">
              <div className="p-2 rounded-md bg-inset text-ink-3 shrink-0 mt-0.5">
                <ShieldAlert className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-sm font-semibold text-ink">
                  Disciplined NO-TRADE State Active (§18)
                </h4>
                <p className="text-xs text-ink-2 mt-0.5 leading-relaxed">
                  Microstructure criteria not fully satisfied. Engine rejects forced trades and preserves capital until high-energy compression snap conditions align.
                </p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

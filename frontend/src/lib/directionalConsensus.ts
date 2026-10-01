/* Unified directional read across the modules an operator used to visit one
   by one: the tactical forecast board, the PAP shadow predictions and the live
   signal book. Every source contributes a signed lean (-100..100) and the
   fusion blends only the sources that actually reported — a missing source
   never votes, it is simply absent. */

import type { PapLive } from '@/lib/api/pap';
import {
  consensusOf,
  type ForecastHorizonId,
} from '@/lib/forecastBoard';
import { horizonDist, predictionTone } from '@/lib/pap';
import type { HourForecast } from '@/lib/types';
import { isTodayIST, type ActiveRow } from '@/lib/signalsNormalize';
import { stageOf } from '@/lib/signalStages';

export type DirectionalSourceId = 'forecast' | 'pap' | 'signals';

export type DirectionalTone = 'bull' | 'bear' | 'neut';

export type DirectionalSourceRead = {
  id: DirectionalSourceId;
  label: string;
  /** Module route an operator can open for the full evidence. */
  href: string;
  tone: DirectionalTone;
  /** Signed lean in -100..100. Null when the source has no directional sample. */
  score: number | null;
  /** Short verdict text, e.g. "BULLISH", "NO DATA". */
  headline: string;
  /** One-line supporting detail. */
  detail: string;
  /** Observations that fed the read (horizons / signals). */
  samples: number;
  /** False when the source is offline or has nothing directional to say. */
  available: boolean;
};

export type DirectionalAlignment = 'ALIGNED' | 'SPLIT' | 'MIXED' | 'NO DATA';

export type DirectionalConsensus = {
  available: boolean;
  tone: DirectionalTone;
  label: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'NO DATA';
  /** Weighted blend of the available source scores, -100..100. */
  score: number;
  /** Conviction = |score|. Zero when nothing directional reported. */
  confidence: number;
  alignment: DirectionalAlignment;
  /** Source vote counts among the sources that reported. */
  bull: number;
  bear: number;
  neut: number;
  sources: DirectionalSourceRead[];
};

/** |score| at or above this is a directional verdict; below it is neutral. */
export const DIRECTION_THRESHOLD = 20;

/* Source weights are deliberately coarse and static: the tactical forecast
   board is the dashboard's native read, the live signal book is execution
   evidence, and PAP is shadow/advisory by contract, so it leans lightest.
   They are exposed for the UI to disclose, never hidden. */
export const SOURCE_WEIGHTS: Record<DirectionalSourceId, number> = {
  forecast: 1.2,
  signals: 1,
  pap: 0.8,
};

function toneLabel(tone: DirectionalTone): 'BULLISH' | 'BEARISH' | 'NEUTRAL' {
  if (tone === 'bull') return 'BULLISH';
  if (tone === 'bear') return 'BEARISH';
  return 'NEUTRAL';
}

export function toneOfScore(score: number | null): DirectionalTone {
  if (score === null) return 'neut';
  if (score >= DIRECTION_THRESHOLD) return 'bull';
  if (score <= -DIRECTION_THRESHOLD) return 'bear';
  return 'neut';
}

/** Signal `direction` is a LONG_CALL / LONG_PUT family token; PUT/BEAR wins
 *  over the residual LONG in "LONG_PUT" so a put is never counted bullish. */
export function signalDirectionTone(direction: unknown): DirectionalTone {
  const s = String(direction ?? '').toUpperCase();
  if (/PUT|BEAR|SHORT/.test(s)) return 'bear';
  if (/CALL|BULL|LONG/.test(s)) return 'bull';
  return 'neut';
}

/** Tactical forecast board: horizon-weighted consensus of the 1m–60m verdicts. */
export function forecastRead(
  forecasts: Partial<Record<ForecastHorizonId, HourForecast | null | undefined>>,
): DirectionalSourceRead {
  const consensus = consensusOf(forecasts);
  const available = consensus.label !== 'NO DATA';
  const samples = consensus.bull + consensus.bear + consensus.neut;
  return {
    id: 'forecast',
    label: 'Tactical forecast',
    href: '/',
    tone: consensus.tone,
    score: available ? consensus.weightedScore : null,
    headline: available ? consensus.label : 'NO DATA',
    detail: available
      ? `${consensus.bull} bull · ${consensus.bear} bear · ${consensus.neut} neutral across ${samples} horizon(s)`
      : 'Forecast board returned no horizon data',
    samples,
    available,
  };
}

function horizonWeight(horizonId: string): number {
  const minutes = /(\d+)\s*m/i.exec(horizonId);
  if (minutes) return Math.sqrt(Math.max(1, Number(minutes[1])));
  const hours = /(\d+)\s*h/i.exec(horizonId);
  if (hours) return Math.sqrt(Math.max(1, Number(hours[1]) * 60));
  return 1;
}

/** PAP shadow predictions: probability-weighted UP/DOWN lean across horizons. */
export function papRead(live: PapLive | null): DirectionalSourceRead {
  const horizons = live?.horizons ? Object.entries(live.horizons) : [];
  if (!live || live.available === false || horizons.length === 0) {
    return {
      id: 'pap',
      label: 'PAP shadow',
      href: '/pap',
      tone: 'neut',
      score: null,
      headline: 'NO DATA',
      detail: live?.unavailable_reason || 'PAP shadow predictions unavailable',
      samples: 0,
      available: false,
    };
  }

  let weighted = 0;
  let weightSum = 0;
  let up = 0;
  let down = 0;
  let flat = 0;

  for (const [id, horizon] of horizons) {
    const dist = horizonDist(horizon);
    const upPct = dist.find((row) => row.label === 'UP')?.pct ?? 0;
    const downPct = dist.find((row) => row.label === 'DOWN')?.pct ?? 0;
    const directional = upPct + downPct;
    const tone = predictionTone(horizon.prediction);
    if (tone === 'bull') up += 1;
    else if (tone === 'bear') down += 1;
    else flat += 1;
    if (directional > 0) {
      const weight = horizonWeight(id);
      weighted += ((upPct - downPct) / directional) * weight;
      weightSum += weight;
    }
  }

  const score = weightSum > 0 ? Math.round((weighted / weightSum) * 100) : null;
  return {
    id: 'pap',
    label: 'PAP shadow',
    href: '/pap',
    tone: toneOfScore(score),
    score,
    headline: score === null ? 'NO DATA' : toneLabel(toneOfScore(score)),
    detail: `${up} up · ${down} down · ${flat} flat across ${horizons.length} horizon(s)`,
    samples: horizons.length,
    available: score !== null,
  };
}

/** Live signal book: today's non-closed long/short balance. */
export function signalsRead(rows: ActiveRow[], nowMs?: number): DirectionalSourceRead {
  let bull = 0;
  let bear = 0;
  let neut = 0;
  let live = 0;

  for (const row of rows) {
    if (stageOf(row.state) === 'CLOSED') continue;
    if (!isTodayIST(row.timeMs, nowMs)) continue;
    live += 1;
    const tone = signalDirectionTone(row.direction);
    if (tone === 'bull') bull += 1;
    else if (tone === 'bear') bear += 1;
    else neut += 1;
  }

  const directional = bull + bear;
  const score = directional > 0 ? Math.round(((bull - bear) / directional) * 100) : null;
  return {
    id: 'signals',
    label: 'Live signals',
    href: '/signals',
    tone: toneOfScore(score),
    score,
    headline: score === null ? (live === 0 ? 'NO LIVE SIGNALS' : 'NO DIRECTION') : toneLabel(toneOfScore(score)),
    detail:
      live === 0
        ? 'No live signals today'
        : `${bull} long · ${bear} short · ${neut} neutral live today`,
    samples: live,
    available: score !== null,
  };
}

/** Blend the source reads into one verdict. Sources that did not report are
 *  excluded from the blend entirely — they contribute no zero vote. */
export function fuseDirectional(reads: DirectionalSourceRead[]): DirectionalConsensus {
  const reporting = reads.filter((read) => read.available && read.score !== null);
  if (reporting.length === 0) {
    return {
      available: false,
      tone: 'neut',
      label: 'NO DATA',
      score: 0,
      confidence: 0,
      alignment: 'NO DATA',
      bull: 0,
      bear: 0,
      neut: 0,
      sources: reads,
    };
  }

  let weighted = 0;
  let weightSum = 0;
  let bull = 0;
  let bear = 0;
  let neut = 0;

  for (const read of reporting) {
    const weight = SOURCE_WEIGHTS[read.id] ?? 1;
    weighted += (read.score as number) * weight;
    weightSum += weight;
    if (read.tone === 'bull') bull += 1;
    else if (read.tone === 'bear') bear += 1;
    else neut += 1;
  }

  const score = weightSum > 0 ? Math.round(weighted / weightSum) : 0;
  const tone = toneOfScore(score);
  const alignment: DirectionalAlignment =
    bull > 0 && bear > 0
      ? 'SPLIT'
      : bull === reporting.length || bear === reporting.length
        ? 'ALIGNED'
        : 'MIXED';

  return {
    available: true,
    tone,
    label: toneLabel(tone),
    score,
    confidence: Math.abs(score),
    alignment,
    bull,
    bear,
    neut,
    sources: reads,
  };
}

/** Read all three modules and return the unified verdict. */
export function buildDirectionalConsensus(input: {
  forecasts: Partial<Record<ForecastHorizonId, HourForecast | null | undefined>>;
  pap: PapLive | null;
  signals: ActiveRow[];
  nowMs?: number;
}): { consensus: DirectionalConsensus; reads: DirectionalSourceRead[] } {
  const reads = [
    forecastRead(input.forecasts),
    signalsRead(input.signals, input.nowMs),
    papRead(input.pap),
  ];
  return { consensus: fuseDirectional(reads), reads };
}

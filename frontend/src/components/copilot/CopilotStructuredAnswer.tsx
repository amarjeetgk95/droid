'use client';

/* Structured Copilot Intelligence Card (DROID spec).

   Replaces free-form text rendering with a canonical information hierarchy:
   - Symbol + horizon header
   - Directional badge (from the canonical enum, never from text parsing)
   - Confidence + regime + data quality
   - Key support/resistance levels
   - Bull/bear triggers
   - Scenarios
   - Evidence grid
   - Conflicts
   - Historical analogs
   - AI explanation

   Tool traces, internal reasoning and raw orchestration are NEVER rendered.
*/

import type { ReactNode } from 'react';
import type { CopilotAnalysisResponse, CopilotDirectionalState, CopilotMarketLevel } from '@/lib/types';

const DIRECTION_TONE: Record<CopilotDirectionalState, string> = {
  BULLISH: 'bull',
  MILD_BULLISH: 'bull',
  NEUTRAL: 'neut',
  MILD_BEARISH: 'bear',
  BEARISH: 'bear',
  NO_SIGNAL: 'warn',
};

const DIRECTION_LABEL: Record<CopilotDirectionalState, string> = {
  BULLISH: 'BULLISH',
  MILD_BULLISH: 'MILD BULLISH',
  NEUTRAL: 'NEUTRAL',
  MILD_BEARISH: 'MILD BEARISH',
  BEARISH: 'BEARISH',
  NO_SIGNAL: 'NO SIGNAL',
};

const HORIZON_LABEL: Record<string, string> = {
  NEXT_15_MIN: 'NEXT 15 MIN',
  NEXT_60_MIN: 'NEXT 60 MIN',
  TODAY: 'TODAY',
  NEXT_SESSION: 'NEXT SESSION',
  SWING_3_5_DAYS: 'SWING 3–5 DAYS',
};

function fmtPrice(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return `₹${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '';
  const sign = v > 0 ? '+' : '';
  return `${sign}${v.toFixed(2)}%`;
}

function levelRow(level: CopilotMarketLevel): ReactNode {
  const sources = (level.source || []).slice(0, 2).join(', ') || '—';
  return (
    <div key={level.price} className="sg-kv">
      <span className="l">{level.type?.replace(/_/g, ' ')}</span>
      <span className="v">
        {fmtPrice(level.price)}
        <span className="sg-note" style={{ marginLeft: 6 }}>
          {sources} · strength {(level.strength * 100).toFixed(0)}%
        </span>
      </span>
    </div>
  );
}

function section(title: string, children: ReactNode, defaultOpen = false) {
  return (
    <details className="card" open={defaultOpen}>
      <summary>{title}</summary>
      <div className="card-bd">{children}</div>
    </details>
  );
}

export function CopilotStructuredAnswer({ data }: { data: CopilotAnalysisResponse }) {
  const { meta, summary, levels, scenarios, evidence, confluence, historical, explanation, data_quality, invalidation, warnings } = data;

  const canonicalDirection = summary.direction as CopilotDirectionalState;
  const tone = DIRECTION_TONE[canonicalDirection] ?? 'warn';
  const directionLabel = DIRECTION_LABEL[canonicalDirection] ?? canonicalDirection;
  const horizon = HORIZON_LABEL[meta.horizon] ?? meta.horizon.replace(/_/g, ' ');
  const freshnessSources = data_quality?.sources ?? [];
  const sourceCount = freshnessSources.filter((s: any) => s.status === 'FRESH').length;

  return (
    <div className="flex flex-col gap-3">
      {/* ---- HEADER ---- */}
      <section className="card" aria-label="Market intelligence header">
        <div className="card-hd">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span className={`badge b-${tone}`} title={`Canonical direction: ${directionLabel}`}>
              {directionLabel}
            </span>
            <span className="card-meta">{meta.symbol}</span>
            <span className="card-meta">{horizon}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            {summary.ltp !== null && summary.ltp !== undefined ? (
              <span className="card-meta num">
                {fmtPrice(summary.ltp)} {fmtPct(summary.change_pct)}
              </span>
            ) : null}
            {summary.confidence !== null && summary.confidence !== undefined ? (
              <span className="stat-chip">
                Confidence <b>{(summary.confidence * 100).toFixed(0)}%</b>
              </span>
            ) : null}
            <span className="card-meta">
              {meta.provider ?? '—'} / {meta.model ?? 'auto'}
            </span>
          </div>
        </div>
        <div className="card-bd">
          <p className="sg-note">
            Regime: <b>{summary.regime?.replace(/_/g, ' ') ?? 'UNKNOWN'}</b>
            {summary.expected_range?.low !== null && summary.expected_range?.high !== null ? (
              <> · Expected range: {fmtPrice(summary.expected_range.low)} – {fmtPrice(summary.expected_range.high)}</>
            ) : null}
          </p>
          <p className="sg-note">
            LIVE · {sourceCount} sources · {meta.latency_ms}ms
            {meta.partial ? ' · partial data' : ''}
          </p>
        </div>
      </section>

      {/* ---- KEY LEVELS ---- */}
      {section('Key levels', (
        <>
          <p className="sg-note">
            <b>Support</b>
          </p>
          {levels.support.length > 0 ? (
            <div className="sg-kvlist">
              {levels.support.map(levelRow)}
            </div>
          ) : <p className="sg-empty">No support levels available.</p>}
          <p className="sg-note" style={{ marginTop: 8 }}>
            <b>Resistance</b>
          </p>
          {levels.resistance.length > 0 ? (
            <div className="sg-kvlist">
              {levels.resistance.map(levelRow)}
            </div>
          ) : <p className="sg-empty">No resistance levels available.</p>}
          {levels.bull_trigger !== null ? (
            <div className="sg-kv" style={{ marginTop: 8 }}>
              <span className="l">Bull trigger</span>
              <span className="v">{levels.bull_trigger_note ?? fmtPrice(levels.bull_trigger)}</span>
            </div>
          ) : null}
          {levels.bear_trigger !== null ? (
            <div className="sg-kv">
              <span className="l">Bear trigger</span>
              <span className="v">{levels.bear_trigger_note ?? fmtPrice(levels.bear_trigger)}</span>
            </div>
          ) : null}
        </>
      ), true)}

      {/* ---- SCENARIOS ---- */}
      {section('Scenarios', (
        <div className="tbl-scroll">
          <table className="sg-table">
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Probability</th>
                <th>Conditions</th>
              </tr>
            </thead>
            <tbody>
              {scenarios.map((s) => (
                <tr key={s.id}>
                  <td>{s.label}</td>
                  <td className="num">
                    {s.probability !== null && s.probability !== undefined
                      ? `${(s.probability * 100).toFixed(0)}%`
                      : 'Probability unavailable'}
                  </td>
                  <td>{(s.conditions || []).join('; ') || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {/* ---- EVIDENCE ---- */}
      {section('Evidence', (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <div>
            <p className="sg-note"><b>Bullish</b></p>
            <ul className="sg-list">
              {(evidence.bullish || []).map((e, i) => <li key={`b${i}`}>{e}</li>)}
              {(!evidence.bullish || evidence.bullish.length === 0) && <li className="sg-empty">None</li>}
            </ul>
          </div>
          <div>
            <p className="sg-note"><b>Bearish</b></p>
            <ul className="sg-list">
              {(evidence.bearish || []).map((e, i) => <li key={`be${i}`}>{e}</li>)}
              {(!evidence.bearish || evidence.bearish.length === 0) && <li className="sg-empty">None</li>}
            </ul>
          </div>
        </div>
      ))}

      {/* ---- CONFLICTS ---- */}
      {(evidence.conflicts || []).length > 0 ? section('Conflicts', (
        <ul className="sg-list">
          {evidence.conflicts.map((c, i) => <li key={i}>{c}</li>)}
        </ul>
      )) : null}

      {/* ---- HISTORICAL ANALOGS ---- */}
      {section('Historical analogs', (
        historical.available ? (
          <div className="sg-kvlist">
            <div className="sg-kv">
              <span className="l">Analog count</span>
              <span className="v">{historical.analog_count} similar sessions</span>
            </div>
            {historical.similarity_threshold !== null ? (
              <div className="sg-kv">
                <span className="l">Similarity threshold</span>
                <span className="v">{(historical.similarity_threshold * 100).toFixed(0)}%</span>
              </div>
            ) : null}
            {historical.forward_outcome ? (
              <div className="sg-kv">
                <span className="l">Forward outcome</span>
                <span className="v">
                  ↑{historical.forward_outcome.positive ?? 0} ·
                  ↔{historical.forward_outcome.neutral ?? 0} ·
                  ↓{historical.forward_outcome.negative ?? 0}
                </span>
              </div>
            ) : null}
            {historical.win_rate !== null ? (
              <div className="sg-kv">
                <span className="l">Win rate</span>
                <span className="v">{(historical.win_rate * 100).toFixed(0)}%</span>
              </div>
            ) : null}
          </div>
        ) : (
          <p className="sg-note">{historical.message || 'Historical analogs unavailable for this analysis.'}</p>
        )
      ))}

      {/* ---- INVALIDATION ---- */}
      {section('Invalidation', (
        <div className="sg-kvlist">
          {invalidation.bullish_trigger ? (
            <div className="sg-kv">
              <span className="l">Bullish trigger</span>
              <span className="v">{invalidation.bullish_trigger}</span>
            </div>
          ) : null}
          {invalidation.bearish_trigger ? (
            <div className="sg-kv">
              <span className="l">Bearish trigger</span>
              <span className="v">{invalidation.bearish_trigger}</span>
            </div>
          ) : null}
          {invalidation.invalidation ? (
            <div className="sg-kv">
              <span className="l">Invalidation</span>
              <span className="v">{invalidation.invalidation}</span>
            </div>
          ) : null}
        </div>
      ))}

      {/* ---- DATA QUALITY ---- */}
      {section('Data quality', (
        <div className="sg-kvlist">
          <div className="sg-kv">
            <span className="l">Overall quality</span>
            <span className="v">{data_quality?.overall ?? 'UNKNOWN'}</span>
          </div>
          {(data_quality?.missing_fields ?? []).length > 0 ? (
            <div className="sg-kv">
              <span className="l">Missing fields</span>
              <span className="v">{(data_quality.missing_fields as string[]).join(', ')}</span>
            </div>
          ) : null}
          {(data_quality?.stale_sources ?? []).length > 0 ? (
            <div className="sg-kv">
              <span className="l">Stale sources</span>
              <span className="v">{(data_quality.stale_sources as string[]).join(', ')}</span>
            </div>
          ) : null}
        </div>
      ))}

      {/* ---- AI EXPLANATION ---- */}
      {section('AI explanation', (
        <p style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {explanation || 'No AI explanation available — analysis uses deterministic evidence only.'}
        </p>
      ))}

      {/* ---- WARNINGS ---- */}
      {warnings.length > 0 ? section('Warnings', (
        <ul className="sg-list">
          {warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )) : null}
    </div>
  );
}

export default CopilotStructuredAnswer;

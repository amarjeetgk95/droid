'use client';

import React from 'react';
import { Badge } from '../shared/Badge';
import { finiteNumber } from './forgeLogic';
import type { AutoDetectCandidate } from '@/lib/api/signals';

interface ConfluenceBreakdownProps {
  candidate?: AutoDetectCandidate | null;
  detected?: boolean;
}

const LAYERS: Array<{ key: keyof AutoDetectCandidate; label: string }> = [
  { key: 'technical_score', label: 'Technical structure' },
  { key: 'mtf_score', label: 'Multi-timeframe alignment' },
  { key: 'fno_score', label: 'F&O positioning' },
  { key: 'regime_score', label: 'Regime fit' },
  { key: 'ai_score', label: 'AI layer' },
];

/**
 * Confluence is computed per candidate by the scanner. Until a candidate is
 * returned there is nothing to show — no hardcoded layer scores are rendered.
 */
export const ConfluenceBreakdown: React.FC<ConfluenceBreakdownProps> = ({ candidate, detected }) => {
  const overall = finiteNumber(candidate?.overall_confidence) ?? finiteNumber(candidate?.confidence);
  const layers = candidate
    ? LAYERS.map((layer) => ({ ...layer, score: finiteNumber(candidate[layer.key]) })).filter(
        (layer): layer is { key: keyof AutoDetectCandidate; label: string; score: number } =>
          layer.score !== null && layer.score >= 0 && layer.score <= 100,
      )
    : [];
  const factors = candidate?.confluence_factors ?? [];
  const direction = typeof candidate?.direction === 'string' ? candidate.direction : null;

  return (
    <div className="p-3.5 rounded-lg bg-surface border border-border shadow-xs font-mono text-xs space-y-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-ink font-semibold">CONFLUENCE WEIGHTING &amp; EXPLAIN BUNDLE</span>
        {candidate && overall !== null ? (
          <span className="text-up-strong font-bold text-sm">{overall}/100</span>
        ) : (
          <Badge variant="neutral" size="xs">
            NO CANDIDATE
          </Badge>
        )}
      </div>

      {!candidate ? (
        <div role="status" className="p-2.5 rounded bg-secondary border border-border text-[11px] text-ink-3 leading-relaxed">
          No candidate evaluated — run Auto-Detect to load the scanner&apos;s confluence bundle.
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2 text-[11px] text-ink-3">
            <span>{typeof candidate.strategy === 'string' ? candidate.strategy : 'Candidate'}</span>
            {direction ? (
              <Badge variant={direction.includes('PUT') ? 'bear' : 'bull'} size="xs">
                {direction}
              </Badge>
            ) : null}
            {detected === false ? (
              <Badge variant="warning" size="xs">
                BASELINE — NO SETUP
              </Badge>
            ) : null}
          </div>

          {layers.length > 0 ? (
            <div className="space-y-2">
              {layers.map((layer) => (
                <div key={String(layer.key)} className="space-y-1">
                  <div className="flex items-center justify-between text-[11px] text-ink-3">
                    <span>{layer.label}</span>
                    <span className="text-ink font-semibold">{layer.score}/100</span>
                  </div>
                  <div className="h-1.5 w-full bg-muted-strong rounded-full overflow-hidden">
                    <div style={{ width: `${layer.score}%` }} className="h-full bg-primary rounded-full" />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="p-2.5 rounded bg-secondary border border-border text-[11px] text-ink-3 leading-relaxed">
              Scanner published no confluence sub-scores for this candidate
              {overall !== null ? ` — overall confidence ${overall}/100.` : '.'}
            </div>
          )}

          {Array.isArray(factors) && factors.length > 0 ? (
            <ul className="text-[11px] text-ink-2 space-y-0.5">
              {factors.map((factor, i) => (
                <li key={i}>• {String(factor)}</li>
              ))}
            </ul>
          ) : null}
        </>
      )}
    </div>
  );
};

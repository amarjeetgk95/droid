'use client';

/* Analyze tab: structured DROID Market Intelligence Copilot.
   Uses POST /api/copilot/analyze which returns a canonical structured response.
   The UI never derives the directional badge from free-form text — it reads
   the canonical `summary.direction` enum from the structured response.
*/

import { useState } from 'react';
import { useInstrument } from '@/context/InstrumentContext';
import { useStructuredCopilotAnalyze } from '@/hooks/useCopilot';
import { copilotErrorHint } from '@/lib/copilot';
import { useToast } from '@/components/ui/toast';
import { CopilotStructuredAnswer } from './CopilotStructuredAnswer';

const HORIZONS = [
  { value: 'NEXT_15_MIN', label: 'Next 15 min' },
  { value: 'NEXT_60_MIN', label: 'Next 60 min' },
  { value: 'TODAY', label: 'Today' },
  { value: 'NEXT_SESSION', label: 'Next session' },
  { value: 'SWING_3_5_DAYS', label: 'Swing 3–5 days' },
] as const;

type Horizon = typeof HORIZONS[number]['value'];

export function AnalyzePanel() {
  const { instrument } = useInstrument();
  const [symbol, setSymbol] = useState<string>(instrument);
  const [query, setQuery] = useState('what\'s next day market prediction');
  const [horizon, setHorizon] = useState<Horizon>('NEXT_SESSION');
  const desk = useStructuredCopilotAnalyze();
  const { push } = useToast();

  const handleAnalyze = async () => {
    const ok = await desk.analyze(symbol, query, horizon);
    if (ok) {
      push('success', 'Analysis complete.');
    } else if (desk.error) {
      push('error', desk.error);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="ds-filters">
        <label className="field">
          <span className="field-l">Symbol</span>
          <input
            className="input"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void handleAnalyze();
            }}
          />
        </label>
        <label className="field">
          <span className="field-l">Query</span>
          <input
            className="input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void handleAnalyze();
            }}
            placeholder="e.g. what's next day market prediction"
          />
        </label>
        <label className="field">
          <span className="field-l">Horizon</span>
          <select
            className="input"
            value={horizon}
            onChange={(e) => setHorizon(e.target.value as Horizon)}
          >
            {HORIZONS.map((h) => (
              <option key={h.value} value={h.value}>{h.label}</option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="btn btn-primary"
          disabled={desk.analyzing}
          onClick={() => void handleAnalyze()}
        >
          {desk.analyzing ? 'Analyzing…' : 'Analyze'}
        </button>
      </div>

      {desk.error ? (
        <div>
          <p className="sg-err">{desk.error}</p>
          <p className="sg-note">{copilotErrorHint(desk.error).hint}</p>
        </div>
      ) : null}

      {desk.response ? (
        <CopilotStructuredAnswer data={desk.response} />
      ) : (
        !desk.analyzing && (
          <p className="sg-note">Run an analysis to render the structured intelligence report.</p>
        )
      )}
    </div>
  );
}

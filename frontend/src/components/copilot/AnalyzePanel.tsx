'use client';

/* Analyze tab: symbol + optional model override -> POST /analyze (or
   /analyze/{symbol}/with-model), report sections + GET /history/{symbol} list. */

import { useState } from 'react';
import { useInstrument } from '@/context/InstrumentContext';
import { useCopilotAnalyze } from '@/hooks/useCopilot';
import { biasTone, copilotErrorHint } from '@/lib/copilot';
import { useToast } from '@/components/ui/toast';
import { CopilotAnswer } from './CopilotAnswer';

export function AnalyzePanel() {
  const { instrument } = useInstrument();
  const [symbol, setSymbol] = useState<string>(instrument);
  const [modelOverride, setModelOverride] = useState('');
  const desk = useCopilotAnalyze();
  const { push } = useToast();

  const handleAnalyze = async () => {
    const ok = await desk.analyze(symbol, modelOverride);
    if (ok) {
      push('success', 'Analysis complete.');
      void desk.loadHistory(symbol);
    } else if (desk.error) {
      const hint = copilotErrorHint(desk.error);
      push('error', desk.error, hint.kind === 'generic' ? undefined : hint.hint);
    }
  };

  const handleHistory = async () => {
    await desk.loadHistory(symbol);
    if (desk.historyError) push('error', desk.historyError);
  };

  const tone = desk.report ? biasTone(desk.report.bias) : 'neut';

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
        <label className="field" title="Blank uses POST /api/v1/ai/analyze with the Settings model; set an ID to use POST /analyze/{symbol}/with-model">
          <span className="field-l">Model override (optional)</span>
          <input
            className="input mono"
            value={modelOverride}
            placeholder="auto — or a model ID"
            onChange={(e) => setModelOverride(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void handleAnalyze();
            }}
          />
        </label>
        <button type="button" className="btn btn-primary" disabled={desk.analyzing} onClick={() => void handleAnalyze()}>
          {desk.analyzing ? 'Analyzing… (up to 180s)' : 'Analyze'}
        </button>
        <button type="button" className="btn" disabled={desk.historyLoading} onClick={() => void handleHistory()}>
          {desk.historyLoading ? 'Loading…' : 'History'}
        </button>
      </div>

      {desk.error ? (
        <div>
          <p className="sg-err">{desk.error}</p>
          <p className="sg-note">{copilotErrorHint(desk.error).hint}</p>
        </div>
      ) : null}

      {desk.report ? (
        <>
          <section className="card" aria-label="Analysis summary">
            <div className="card-hd">
              <h2 className="card-title">Report</h2>
              <span className={`badge b-${tone}`}>{desk.report.bias}</span>
              <span className="card-meta num">
                {desk.report.symbol}
                {desk.report.confidence !== null ? ` · ${desk.report.confidence.toFixed(1)}%` : ''}
                {desk.modelUsed ? ` · ${desk.modelUsed}` : ''}
              </span>
            </div>
            <div className="card-bd">
              <CopilotAnswer raw={desk.report.summary} confidence={desk.report.confidence} providerLabel={`${desk.report.timestamp} · ${desk.report.provider}${desk.modelUsed ? ` · ${desk.modelUsed}` : ''}`} />
            </div>
          </section>
          {desk.report.sections.map((s, i) => (
            <details key={s.label} className="card" aria-label={s.label} open={i === 0 ? true : undefined}>
              <summary>{s.label}</summary>
              <CopilotAnswer raw={s.text} />
            </details>
          ))}
        </>
      ) : (
        !desk.analyzing && <p className="sg-note">Run an analysis to render the structured report sections here.</p>
      )}

      <section className="card" aria-label="Analysis history">
        <div className="card-hd">
          <h2 className="card-title">History</h2>
          <span className="card-meta num">{desk.history.length}</span>
        </div>
        <div className="card-bd">
          {desk.historyError ? <p className="sg-err">{desk.historyError}</p> : null}
          {desk.history.length === 0 ? (
            <p className="sg-empty">No past reports loaded for this symbol yet.</p>
          ) : (
            <div className="tbl-scroll">
              <table className="sg-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Symbol</th>
                    <th>Bias</th>
                    <th>Conf</th>
                    <th>Summary</th>
                  </tr>
                </thead>
                <tbody>
                  {desk.history.map((row) => (
                    <tr key={row.id}>
                      <td className="num">{row.timestamp}</td>
                      <td>
                        <span className="sg-sym">{row.symbol}</span>
                      </td>
                      <td>
                        <span className={`sg-tag ${biasTone(row.bias)}`}>{row.bias}</span>
                      </td>
                      <td className="num">{row.confidence !== null ? row.confidence.toFixed(1) : '—'}</td>
                      <td>
                        <span className="sg-rownote">{row.summary}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

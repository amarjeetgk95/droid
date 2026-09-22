'use client';

/* Briefing tab: instrument-aware GET /briefing/{symbol} + /deep-insight/{symbol} cards with refresh. */

import { useState } from 'react';
import { CopilotAnswer } from './CopilotAnswer';
import { useInstrument } from '@/context/InstrumentContext';
import { useCopilotBriefing } from '@/hooks/useCopilot';
import { useToast } from '@/components/ui/toast';
import { errorMessage } from '@/lib/errors';

const SESSIONS = ['PRE_MARKET', 'POST_MARKET', 'INTRADAY_UPDATE'] as const;

export function BriefingPanel() {
  const { instrument } = useInstrument();
  const [draft, setDraft] = useState<string>(instrument);
  const [applied, setApplied] = useState<string>(instrument);
  const desk = useCopilotBriefing(applied);
  const { push } = useToast();

  const apply = async (next?: string) => {
    const value = (next ?? draft).trim().toUpperCase() || instrument;
    setDraft(value);
    setApplied(value);
  };

  const handleRefresh = async () => {
    try {
      await desk.refresh();
      push('success', 'Briefing refreshed.');
    } catch (err) {
      push('error', errorMessage(err, 'Briefing refresh failed'));
    }
  };

  const card = desk.briefing;

  return (
    <div className="flex flex-col gap-3">
      <div className="ds-filters">
        <label className="field">
          <span className="field-l">Symbol</span>
          <input
            className="input"
            value={draft}
            onChange={(e) => setDraft(e.target.value.toUpperCase())}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void apply();
            }}
          />
        </label>
        <span className="seg" title="Briefing session">
          {SESSIONS.map((s) => (
            <button
              key={s}
              type="button"
              className="seg-btn"
              data-active={desk.session === s}
              onClick={() => desk.setSession(s)}
            >
              {s.replace('_', ' ')}
            </button>
          ))}
        </span>
        <button type="button" className="btn btn-ic" onClick={() => void apply()}>
          Load
        </button>
        <button type="button" className="btn" disabled={desk.refreshing} onClick={() => void handleRefresh()}>
          {desk.refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {desk.error ? <p className="sg-err">{desk.error}</p> : null}

      {desk.loading ? (
        <div className="panel">
          <p className="sg-empty">Loading briefing…</p>
        </div>
      ) : card ? (
        <>
          <section className="card" aria-label="Executive briefing">
            <div className="card-hd">
              <h2 className="card-title">Briefing</h2>
              <span className="card-meta num">
                {card.symbol} · {card.session}
              </span>
            </div>
            <div className="card-bd">
              <CopilotAnswer
                raw={card.summary}
                providerLabel={`${card.timestamp} · ${card.provider}`}
                provider={card.provider}
              />
            </div>
          </section>

          <section className="card" aria-label="Key levels">
            <div className="card-hd">
              <h2 className="card-title">Key levels</h2>
              <span className="card-meta num" title="Levels are only as fresh as the briefing payload that produced them.">
                source {card.provider} · as of {card.timestamp}
              </span>
            </div>
            <div className="card-bd">
              {card.levels.length === 0 ? (
                <p className="sg-empty">No levels returned.</p>
              ) : (
                <div className="sg-kvlist">
                  {card.levels.slice(0, 6).map((l) => (
                    <div key={l.label} className="sg-kv" title={`${l.label}: ${l.value} (${card.provider} · ${card.timestamp})`}>
                      <span className="l">{l.label}</span>
                      <span className="v num">{l.value}</span>
                    </div>
                  ))}
                </div>
              )}
              {card.pinPivots !== '—' || card.fiiDii !== '—' ? (
                <span className="stat-chips">
                  {card.pinPivots !== '—' ? (
                    <span
                      className="stat-chip"
                      title={`${card.pinPivots} — ${card.provider} · ${card.timestamp}`}
                      style={{
                        whiteSpace: 'normal',
                        display: '-webkit-box',
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical',
                        overflow: 'hidden',
                      }}
                    >
                      {card.pinPivots}
                    </span>
                  ) : null}
                  {card.fiiDii !== '—' ? (
                    <span
                      className="stat-chip"
                      title={`${card.fiiDii} — ${card.provider} · ${card.timestamp}`}
                      style={{
                        whiteSpace: 'normal',
                        display: '-webkit-box',
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical',
                        overflow: 'hidden',
                      }}
                    >
                      FII/DII: {card.fiiDii}
                    </span>
                  ) : null}
                </span>
              ) : (
                <p className="sg-note">No pin/pivot or FII/DII readout in this briefing payload.</p>
              )}
            </div>
          </section>

          <section className="card" aria-label="Actionable playbook">
            <div className="card-hd">
              <h2 className="card-title">Playbook</h2>
            </div>
            <div className="card-bd">
              {card.playbook.length === 0 ? (
                <p className="sg-empty">No playbook steps returned.</p>
              ) : (
                <div className="flex flex-col gap-2">
                  {card.playbook.slice(0, 3).map((step, i) => (
                    <p key={i} className="sg-rownote">
                      {step}
                    </p>
                  ))}
                  {card.playbook.length > 3 ? (
                    <details>
                      <summary className="sg-rownote">Show all {card.playbook.length}</summary>
                      <div className="flex flex-col gap-2">
                        {card.playbook.slice(3).map((step, i) => (
                          <p key={i + 3} className="sg-rownote">
                            {step}
                          </p>
                        ))}
                      </div>
                    </details>
                  ) : null}
                </div>
              )}
            </div>
          </section>
        </>
      ) : null}

      <section className="card" aria-label="Deep insight">
        <div className="card-hd">
          <h2 className="card-title">Deep insight</h2>
          <span className="card-meta">{applied}</span>
        </div>
        <div className="card-bd">
          {desk.deepError ? <p className="sg-err">{desk.deepError}</p> : null}
          {desk.deepRows.length === 0 && !desk.deepError ? (
            <p className="sg-empty">No deep-insight fields returned.</p>
          ) : (
            <>
              <div className="sg-kvlist">
                {desk.deepRows.slice(0, 6).map((row) => (
                  <div key={row.label} className="sg-kv" title={`${row.label}: ${row.value}`}>
                    <span className="l">{row.label.split('.').pop()?.replace(/_/g, ' ') ?? row.label}</span>
                    <span className="v">{row.value}</span>
                  </div>
                ))}
              </div>
              {desk.deepRows.length > 6 ? (
                <details>
                  <summary className="sg-rownote">Show all {desk.deepRows.length}</summary>
                  <div className="sg-kvlist">
                    {desk.deepRows.slice(6).map((row) => (
                      <div key={row.label} className="sg-kv" title={`${row.label}: ${row.value}`}>
                        <span className="l">{row.label.split('.').pop()?.replace(/_/g, ' ') ?? row.label}</span>
                        <span className="v">{row.value}</span>
                      </div>
                    ))}
                  </div>
                </details>
              ) : null}
            </>
          )}
        </div>
      </section>
    </div>
  );
}

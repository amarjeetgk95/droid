'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { X } from 'lucide-react';
import { api } from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import { getObj, pickMs, pickNum, pickStr } from '@/lib/signalsNormalize';
import { SIGNAL_STAGES, STAGE_META, closedOutcome, stageIndex, stageOf } from '@/lib/signalStages';
import { Meter } from '@/components/ui/desk';
import { safeNum } from '@/lib/utils';
import { OptionPayoffDiagram } from '@/components/ui/OptionPayoffDiagram';
import { GreeksBarometer } from '@/components/ui/GreeksBarometer';

type DeepDive = {
  signal?: Record<string, unknown> | null;
  explain?: Record<string, unknown> | null;
  confluence?: Record<string, unknown> | null;
  option_contract?: Record<string, unknown> | null;
  fsm_history?: unknown[] | null;
  position_sizing_preview?: Record<string, unknown> | null;
  levels?: Record<string, unknown> | null;
  current_market_price?: number | null;
  threshold_armed?: number | null;
  weights_version?: number | null;
};

function fmtTime(ms: number | null): string {
  if (ms === null) return '—';
  return new Date(ms).toLocaleTimeString('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="sg-kv">
      <span className="l">{label}</span>
      <span className="v">{value}</span>
    </div>
  );
}

/** Non-empty strings from a loose JSON list. */
function strList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((v): v is string => typeof v === 'string' && v.trim() !== '');
}

/** Scalar key/values from a loose JSON object (numbers, strings, booleans, short string lists). */
function scalarRows(obj: Record<string, unknown> | null, limit = 14): Array<[string, string]> {
  if (!obj) return [];
  const rows: Array<[string, string]> = [];
  for (const [key, value] of Object.entries(obj)) {
    if (value === null || value === undefined) continue;
    if (typeof value === 'number' && Number.isFinite(value)) rows.push([key, safeNum(value)]);
    else if (typeof value === 'string' && value !== '') rows.push([key, value]);
    else if (typeof value === 'boolean') rows.push([key, value ? 'yes' : 'no']);
    else if (
      Array.isArray(value) &&
      value.length > 0 &&
      value.length <= 12 &&
      value.every((v) => typeof v === 'string' || typeof v === 'number')
    ) {
      rows.push([key, value.join(', ')]);
    }
    if (rows.length >= limit) break;
  }
  return rows;
}

type VoteRow = {
  domain: string;
  label: string;
  score: number | null;
  weight: number | null;
  points: number | null;
};

/** Domain vote rows from the explain bundle's `maths` list. */
function voteRows(list: unknown): VoteRow[] {
  if (!Array.isArray(list)) return [];
  const rows: VoteRow[] = [];
  for (const item of list) {
    const o = getObj(item);
    if (!o) continue;
    rows.push({
      domain: pickStr(o, 'domain') ?? '—',
      label: pickStr(o, 'label') ?? pickStr(o, 'domain') ?? '—',
      score: pickNum(o, 'score'),
      weight: pickNum(o, 'weight'),
      points: pickNum(o, 'points'),
    });
  }
  return rows;
}

export function SignalDetailDrawer({
  signalId,
  onClose,
}: {
  signalId: string | null;
  onClose: () => void;
}) {
  const [data, setData] = useState<DeepDive | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!signalId) {
      setData(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    void (async () => {
      try {
        const result = await api.getSignalDeepDive(signalId);
        if (!cancelled) setData(result as DeepDive);
      } catch (err) {
        if (!cancelled) setError(errorMessage(err, 'Dossier unavailable'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [signalId]);

  useEffect(() => {
    if (!signalId) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [signalId, onClose]);

  const signal = useMemo(() => getObj(data?.signal ?? null), [data?.signal]);
  const levels = useMemo(() => getObj(data?.levels ?? null), [data?.levels]);
  const contract = useMemo(() => getObj(data?.option_contract ?? null), [data?.option_contract]);
  const entries = useMemo(() => {
    const list = Array.isArray(data?.fsm_history) ? data.fsm_history : [];
    return list
      .map((entry) => getObj(entry))
      .filter((entry): entry is Record<string, unknown> => entry !== null)
      .sort(
        (a, b) => (pickMs(a, 'processed_timestamp') ?? 0) - (pickMs(b, 'processed_timestamp') ?? 0),
      );
  }, [data?.fsm_history]);
  const confluence = useMemo(() => {
    const record = getObj(data?.confluence ?? null);
    if (!record) return [];
    return Object.entries(record)
      .filter(([, value]) => typeof value === 'number' || typeof value === 'string' || typeof value === 'boolean')
      .slice(0, 10);
  }, [data?.confluence]);
  const confluenceLists = useMemo(() => {
    const record = getObj(data?.confluence ?? null);
    if (!record) return [];
    return Object.entries(record).filter(
      (entry): entry is [string, string[]] =>
        Array.isArray(entry[1]) &&
        entry[1].length > 0 &&
        entry[1].every((v) => typeof v === 'string'),
    );
  }, [data?.confluence]);

  const explain = useMemo(() => getObj(data?.explain ?? null), [data?.explain]);
  const verdict = useMemo(() => getObj(explain?.verdict ?? null), [explain]);
  const votes = useMemo(() => voteRows(explain?.maths), [explain]);
  const penalties = useMemo(() => strList(explain?.penalties), [explain]);
  const whyBullets = useMemo(() => strList(explain?.why_layman), [explain]);
  const changeMind = useMemo(() => strList(explain?.what_would_change_mind), [explain]);
  const gatesPassed = useMemo(() => strList(explain?.gates_passed), [explain]);
  const strategyRule = useMemo(
    () => (typeof explain?.strategy_rule === 'string' ? explain.strategy_rule : null),
    [explain],
  );
  const rationale = useMemo(() => strList(signal?.rationale), [signal]);
  const greeks = useMemo(() => getObj(signal?.greeks ?? null), [signal]);
  const expectedMove = useMemo(() => getObj(signal?.expected_move ?? null), [signal]);
  const pathSim = useMemo(() => getObj(signal?.path_simulation ?? null), [signal]);
  const sizing = useMemo(
    () => getObj(data?.position_sizing_preview ?? null),
    [data?.position_sizing_preview],
  );

  const handleBackdrop = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      if (event.target === event.currentTarget) onClose();
    },
    [onClose],
  );

  if (!signalId) return null;

  const state = signal ? pickStr(signal, 'fsm_state', 'status', 'state') ?? '—' : '—';
  const stage = stageOf(state);
  const outcome = stage === 'CLOSED' ? closedOutcome(state) : null;
  const riskReward1 = levels ? pickNum(levels, 'risk_reward_t1') : signal ? pickNum(signal, 'risk_reward_t1') : null;
  const riskReward2 = levels ? pickNum(levels, 'risk_reward_t2') : signal ? pickNum(signal, 'risk_reward_t2') : null;

  return (
    <div className="sg-ovl" role="presentation" onClick={handleBackdrop}>
      <aside className="sg-drawer" role="dialog" aria-modal="true" aria-label="Signal dossier">
        <header className="sg-dhead">
          <div className="min-w-0">
            <div className="sg-eyebrow">SIGNAL DOSSIER</div>
            <h2 className="sg-dtitle truncate">
              {signal ? `${pickStr(signal, 'underlying') ?? '—'} · ${pickStr(signal, 'strategy') ?? '—'}` : 'Loading…'}
            </h2>
            <div className="sg-dtags">
              <span className={`sg-tag ${outcome === 'WIN' ? 'bull' : outcome === 'LOSS' ? 'bear' : 'info'}`}>
                {state}
              </span>
              <span className="sg-num">{signalId.slice(0, 12)}</span>
              {riskReward1 !== null ? <span className="sg-tag neut">R:R {safeNum(riskReward1)}</span> : null}
            </div>
          </div>
          <button type="button" className="sg-ibtn" onClick={onClose} aria-label="Close dossier">
            <X size={14} />
          </button>
        </header>

        <div className="flex items-center gap-1 border-b border-border-subtle px-3 py-2">
          {SIGNAL_STAGES.map((entry, index) => (
            <span
              key={entry}
              className={`sg-tag ${index <= stageIndex(stage) ? 'info' : 'neut'}`}
              title={STAGE_META[entry].description}
            >
              {STAGE_META[entry].label}
            </span>
          ))}
        </div>

        <div className="sg-dbody">
          {loading ? <p className="sg-note">Loading dossier…</p> : null}
          {error ? <p className="sg-err">{error}</p> : null}

          {explain || verdict ? (
            <section>
              <h3 className="sg-sect">Why this signal</h3>
              <div className="sg-kvlist">
                <Row
                  label="Verdict"
                  value={`${pickStr(verdict ?? {}, 'direction') ?? '—'} · ${safeNum(pickNum(verdict ?? {}, 'confidence'))}${data?.threshold_armed != null ? ` / armed ${safeNum(data.threshold_armed, '—', 0)}` : ''}`}
                />
                <Row label="State" value={pickStr(verdict ?? {}, 'state') ?? '—'} />
                {strategyRule ? <Row label="Playbook" value={strategyRule} /> : null}
              </div>
              {whyBullets.map((bullet, index) => (
                <p key={index} className="sg-note">• {bullet}</p>
              ))}
              {changeMind.length > 0 ? (
                <p className="sg-note">What would change this: {changeMind.join(' · ')}</p>
              ) : null}
              {penalties.map((penalty, index) => (
                <p key={index} className="sg-err">• {penalty}</p>
              ))}
            </section>
          ) : null}

          {votes.length > 0 ? (
            <section>
              <h3 className="sg-sect">Domain votes</h3>
              <div className="sg-kvlist">
                {votes.map((vote) => (
                  <div key={vote.domain} className="sg-kv">
                    <span className="l">{vote.label}</span>
                    <span className="v">
                      {safeNum(vote.score)}
                      {vote.weight !== null ? ` · w${safeNum(vote.weight, '—', 2)}` : ''}
                      {vote.points !== null ? ` · ${vote.points >= 0 ? '+' : ''}${safeNum(vote.points, '—', 1)}` : ''}
                    </span>
                  </div>
                ))}
              </div>
              {votes.map((vote) => (
                <Meter
                  key={`meter-${vote.domain}`}
                  value={vote.score !== null ? vote.score / 100 : 0}
                  label={`${vote.label} score`}
                />
              ))}
              {gatesPassed.length > 0 ? (
                <p className="sg-note">Gates passed: {gatesPassed.join(', ')}</p>
              ) : null}
            </section>
          ) : null}

          {rationale.length > 0 ? (
            <section>
              <h3 className="sg-sect">Analyst notes (AI · ML · flow)</h3>
              {rationale.map((line, index) => (
                <p key={index} className="sg-note">• {line}</p>
              ))}
            </section>
          ) : null}

          {signal ? (
            <section>
              <h3 className="sg-sect">Levels</h3>
              <div className="sg-kvlist">
                <Row label="Spot at detection" value={safeNum(pickNum(signal, 'spot_price'))} />
                <Row label="Entry range" value={levels && Array.isArray(levels.entry_range) ? (levels.entry_range as unknown[]).map((v) => safeNum(Number(v))).join(' – ') : '—'} />
                <Row label="Trigger" value={safeNum(pickNum(levels ?? signal, 'trigger'))} />
                <Row label="Stop loss" value={safeNum(pickNum(levels ?? signal, 'stop_loss'))} />
                <Row label="Target 1" value={safeNum(pickNum(levels ?? signal, 'target_1'))} />
                <Row label="Target 2" value={safeNum(pickNum(levels ?? signal, 'target_2'))} />
                <Row label="Risk points" value={safeNum(pickNum(levels ?? signal, 'risk_points'))} />
                <Row label="R:R T1 / T2" value={`${safeNum(riskReward1)} / ${safeNum(riskReward2)}`} />
                <Row label="Current market" value={safeNum(data?.current_market_price)} />
              </div>
            </section>
          ) : null}

          {signal ? (
            <section>
              <h3 className="sg-sect">Execution</h3>
              <div className="sg-kvlist">
                <Row label="Fill price" value={safeNum(pickNum(signal, 'actual_fill_price'))} />
                <Row label="Intended qty" value={safeNum(pickNum(signal, 'intended_qty'), '—', 0)} />
                <Row label="Remaining qty" value={safeNum(pickNum(signal, 'remaining_qty'), '—', 0)} />
                <Row label="Exit price" value={safeNum(pickNum(signal, 'exit_price'))} />
                <Row label="Realized R (net)" value={safeNum(pickNum(signal, 'realized_rr_net'))} />
                <Row label="Terminal outcome" value={pickStr(signal, 'terminal_outcome') ?? '—'} />
                <Row label="Outcome status" value={pickStr(signal, 'outcome_status') ?? '—'} />
                <Row label="Execution eligible" value={signal.execution_eligibility === false ? 'NO' : 'YES'} />
                <Row label="Created" value={pickStr(signal, 'created_at_str') ?? fmtTime(pickMs(signal, 'created_at_utc'))} />
                <Row label="TTL" value={pickNum(signal, 'ttl_seconds') !== null ? `${pickNum(signal, 'ttl_seconds')}s` : '—'} />
              </div>
            </section>
          ) : null}

          {contract ? (
            <section>
              <h3 className="sg-sect">Option Contract</h3>
              <div className="sg-kvlist">
                <Row label="Symbol" value={pickStr(contract, 'symbol') ?? '—'} />
                <Row label="Strike" value={safeNum(pickNum(contract, 'strike'))} />
                <Row label="Type" value={pickStr(contract, 'option_type') ?? '—'} />
                <Row label="Expiry" value={pickStr(contract, 'expiry') ?? '—'} />
                <Row label="Lot size" value={safeNum(pickNum(contract, 'lot_size'), '—', 0)} />
              </div>
            </section>
          ) : null}

          {contract || (signal && pickNum(signal, 'strike')) ? (
            <section className="flex flex-col gap-1.5">
              <h3 className="sg-sect">Payoff Curve (Expiry)</h3>
              <OptionPayoffDiagram
                direction={pickStr(contract ?? {}, 'option_type') ?? pickStr(signal ?? {}, 'direction') ?? 'LONG_CALL'}
                strike={pickNum(contract ?? {}, 'strike') ?? pickNum(signal ?? {}, 'strike') ?? 0}
                entryPremium={pickNum(signal ?? {}, 'actual_fill_price') ?? pickNum(signal ?? {}, 'option_premium') ?? pickNum(contract ?? {}, 'last_price') ?? 100}
                lotSize={pickNum(contract ?? {}, 'lot_size') ?? pickNum(signal ?? {}, 'lot_size') ?? 25}
                currentSpot={data?.current_market_price ?? pickNum(signal ?? {}, 'spot_price')}
                target1Spot={pickNum(levels ?? signal ?? {}, 'target_1')}
                target2Spot={pickNum(levels ?? signal ?? {}, 'target_2')}
                stopLossSpot={pickNum(levels ?? signal ?? {}, 'stop_loss')}
              />
            </section>
          ) : null}

          {greeks ? (
            <section className="flex flex-col gap-1.5">
              <h3 className="sg-sect">Greeks Barometer</h3>
              <GreeksBarometer
                delta={pickNum(greeks, 'delta') ?? (signal ? pickNum(signal, 'option_delta') : null)}
                theta={pickNum(greeks, 'theta') ?? (signal ? pickNum(signal, 'option_theta') : null)}
                gamma={pickNum(greeks, 'gamma')}
                vega={pickNum(greeks, 'vega')}
                iv={pickNum(greeks, 'iv')}
                lotSize={pickNum(contract ?? {}, 'lot_size') ?? 25}
              />
            </section>
          ) : null}

          {greeks || expectedMove || pathSim ? (
            <section>
              <h3 className="sg-sect">Options math</h3>
              <div className="sg-kvlist">
                {scalarRows(greeks).map(([key, value]) => (
                  <Row key={`greeks-${key}`} label={key.replace(/_/g, ' ')} value={value} />
                ))}
                {scalarRows(expectedMove).map(([key, value]) => (
                  <Row key={`em-${key}`} label={key.replace(/_/g, ' ')} value={value} />
                ))}
                {scalarRows(pathSim).map(([key, value]) => (
                  <Row key={`ps-${key}`} label={key.replace(/_/g, ' ')} value={value} />
                ))}
              </div>
            </section>
          ) : null}

          {sizing ? (
            <section>
              <h3 className="sg-sect">Sizing preview (2% risk)</h3>
              {Object.entries(sizing).map(([account, payload]) => {
                const rows = scalarRows(getObj(payload));
                if (rows.length === 0) return null;
                return (
                  <div key={account}>
                    <p className="sg-note">{account.replace(/_/g, ' ')}</p>
                    <div className="sg-kvlist">
                      {rows.map(([key, value]) => (
                        <Row key={`${account}-${key}`} label={key.replace(/_/g, ' ')} value={value} />
                      ))}
                    </div>
                  </div>
                );
              })}
            </section>
          ) : null}

          <section>
            <h3 className="sg-sect">Stage timeline</h3>
            {entries.length === 0 ? (
              <p className="sg-note">No transitions recorded yet — the signal is at its initial stage.</p>
            ) : (
              <ol className="sg-tl">
                {entries.map((entry, index) => {
                  const from = pickStr(entry, 'from_state') ?? '—';
                  const to = pickStr(entry, 'to_state') ?? '—';
                  const reason = pickStr(entry, 'reason_code') ?? '';
                  const price = pickNum(entry, 'market_price');
                  return (
                    <li key={pickStr(entry, 'transition_id') ?? index}>
                      <span className="sg-num">{fmtTime(pickMs(entry, 'processed_timestamp'))}</span>
                      <span className="sg-tl-trans">
                        {from} → {to}
                      </span>
                      {price !== null ? <span className="sg-num">@ {safeNum(price)}</span> : null}
                      {reason ? <span className="sg-tl-reason">{reason}</span> : null}
                    </li>
                  );
                })}
              </ol>
            )}
          </section>

          {confluence.length > 0 || confluenceLists.length > 0 ? (
            <section>
              <h3 className="sg-sect">Confluence breakdown</h3>
              <div className="sg-kvlist">
                {confluence.map(([key, value]) => (
                  <Row
                    key={key}
                    label={key.replace(/_/g, ' ')}
                    value={typeof value === 'number' ? safeNum(value) : String(value)}
                  />
                ))}
                {confluenceLists.map(([key, values]) => (
                  <Row key={key} label={key.replace(/_/g, ' ')} value={values.join(' · ')} />
                ))}
              </div>
              {data?.threshold_armed != null ? (
                <p className="sg-note">Armed threshold: {safeNum(data.threshold_armed)} · weights v{data.weights_version ?? '—'}</p>
              ) : null}
            </section>
          ) : null}
        </div>
      </aside>
    </div>
  );
}

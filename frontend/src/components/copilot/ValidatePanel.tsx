'use client';

/* Validate tab: trade-setup form -> POST /trade/validate verdict card,
   strategy form -> POST /strategy/recommend, plus POST /test and the
   models catalog strip (GET /models, /models/cache-status, POST /models/refresh). */

import { useState } from 'react';
import { useInstrument } from '@/context/InstrumentContext';
import { useCopilotValidate, type ModelsCache } from '@/hooks/useCopilot';
import { biasTone, copilotErrorHint } from '@/lib/copilot';
import { useToast } from '@/components/ui/toast';
import { CopilotAnswer } from './CopilotAnswer';

function parseNum(raw: string): number | null {
  const n = Number(raw.trim());
  return raw.trim() !== '' && Number.isFinite(n) ? n : null;
}

const OUTLOOKS = ['BULLISH', 'BEARISH', 'NEUTRAL', 'HIGH_VOLATILITY', 'LOW_VOLATILITY', 'DIRECTIONAL_RANGE'] as const;
const RISKS = ['LOW', 'MODERATE', 'AGGRESSIVE'] as const;

const KV_CLAMP = 140;

function clamp140(value: string): string {
  return value.length > KV_CLAMP ? `${value.slice(0, KV_CLAMP)}…` : value;
}

function KvClamped({ label, value }: { label: string; value: string }) {
  const long = value.length > KV_CLAMP;
  return (
    <div className="sg-kv">
      <span className="l">{label}</span>
      <span className="v" title={long ? value : undefined}>
        {clamp140(value)}
        {long ? (
          <details>
            <summary>Show full</summary>
            <span>{value}</span>
          </details>
        ) : null}
      </span>
    </div>
  );
}

function CappedBullets({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  const head = items.slice(0, 3);
  const rest = items.slice(3);
  return (
    <div className="sg-note">
      <span>
        {label}:{' '}
      </span>
      <ul>
        {head.map((t, i) => (
          <li key={i}>{t}</li>
        ))}
      </ul>
      {rest.length > 0 ? (
        <details>
          <summary>Show all ({items.length})</summary>
          <ul>
            {rest.map((t, i) => (
              <li key={i + 3}>{t}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

function RiskClamped({ text }: { text: string }) {
  const long = text.length > 160;
  return (
    <div className="sg-note">
      <span>Risk: </span>
      <span
        style={{
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}
      >
        {text}
      </span>
      {long ? (
        <details>
          <summary>Show full</summary>
          <span>{text}</span>
        </details>
      ) : null}
    </div>
  );
}

export function ValidatePanel({
  totalCount,
  freeCount,
  paidCount,
  cache,
  modelsRefreshing,
  modelsError,
  onRefreshModels,
}: {
  totalCount: number | null;
  freeCount: number | null;
  paidCount: number | null;
  cache: ModelsCache | null;
  modelsRefreshing: boolean;
  modelsError: string | null;
  onRefreshModels: () => void;
}) {
  const { instrument } = useInstrument();
  const [symbol, setSymbol] = useState<string>(instrument);
  const [direction, setDirection] = useState<'BUY' | 'SELL'>('BUY');
  const [entry, setEntry] = useState('');
  const [stop, setStop] = useState('');
  const [target, setTarget] = useState('');
  const [thesis, setThesis] = useState('');
  const [outlook, setOutlook] = useState<(typeof OUTLOOKS)[number]>('NEUTRAL');
  const [risk, setRisk] = useState<(typeof RISKS)[number]>('MODERATE');
  const [query, setQuery] = useState('');
  const desk = useCopilotValidate();
  const { push } = useToast();

  const handleValidate = async () => {
    const entryN = parseNum(entry);
    const stopN = parseNum(stop);
    const targetN = parseNum(target);
    if (entryN === null || stopN === null || targetN === null) {
      push('error', 'Entry, stop and target must all be numbers.');
      return;
    }
    const ok = await desk.validateTrade({
      symbol,
      direction,
      entry: entryN,
      stop: stopN,
      target: targetN,
      thesis,
    });
    push(ok ? 'success' : 'error', ok ? `Trade verdict: ${desk.verdict?.decision ?? 'recorded'}.` : (desk.error ?? 'Validation failed.'));
  };

  const handleStrategy = async () => {
    const ok = await desk.recommendStrategy({ symbol, outlook, risk, query });
    push(ok ? 'success' : 'error', ok ? `Strategy: ${desk.strategy?.name ?? 'recorded'}.` : (desk.error ?? 'Recommendation failed.'));
  };

  const handleTest = async () => {
    const ok = await desk.runTest(symbol);
    if (ok) {
      const r = desk.testResult;
      push('success', `Backend OK — ${r?.provider ?? '?'}${r?.latencyMs !== null ? ` in ${r?.latencyMs}ms` : ''}.`);
    } else {
      push('error', desk.testResult?.detail ?? desk.error ?? 'Backend check failed.');
    }
  };

  const verdictTone = desk.verdict ? biasTone(desk.verdict.decision) : 'neut';

  return (
    <div className="flex flex-col gap-3">
      <div className="ds-filters">
        <label className="field">
          <span className="field-l">Symbol</span>
          <input className="input" value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} />
        </label>
        <span className="stat-chips">
          <span className="stat-chip">
            models <b>{totalCount ?? '—'}</b>
          </span>
          <span className="stat-chip">
            free <b>{freeCount ?? '—'}</b>
          </span>
          <span className="stat-chip">
            paid <b>{paidCount ?? '—'}</b>
          </span>
          <span className="stat-chip" title="OpenRouter catalog cache">
            cache <b>{cache ? `${cache.usingCached ? 'cached' : 'live'}${cache.ageSeconds !== null ? ` ${cache.ageSeconds}s` : ''}` : '—'}</b>
          </span>
        </span>
        <button type="button" className="btn" disabled={modelsRefreshing} onClick={onRefreshModels}>
          {modelsRefreshing ? 'Refreshing…' : 'Refresh models'}
        </button>
      </div>
      {modelsError ? <p className="sg-err">{modelsError}</p> : null}

      <section className="card" aria-label="Trade setup validation">
        <div className="card-hd">
          <h2 className="card-title">Validate setup</h2>
          <span className="card-meta">POST /trade/validate</span>
        </div>
        <div className="card-bd">
          <div className="ds-filters">
            <span className="seg" title="Direction">
              {(['BUY', 'SELL'] as const).map((d) => (
                <button key={d} type="button" className="seg-btn" data-active={direction === d} onClick={() => setDirection(d)}>
                  {d}
                </button>
              ))}
            </span>
            <label className="field">
              <span className="field-l">Entry</span>
              <input className="input num" inputMode="decimal" value={entry} onChange={(e) => setEntry(e.target.value)} />
            </label>
            <label className="field">
              <span className="field-l">Stop</span>
              <input className="input num" inputMode="decimal" value={stop} onChange={(e) => setStop(e.target.value)} />
            </label>
            <label className="field">
              <span className="field-l">Target</span>
              <input className="input num" inputMode="decimal" value={target} onChange={(e) => setTarget(e.target.value)} />
            </label>
            <button type="button" className="btn btn-primary" disabled={desk.busy === 'validate'} onClick={() => void handleValidate()}>
              {desk.busy === 'validate' ? 'Validating… (up to 180s)' : 'Validate'}
            </button>
          </div>
          <label className="field">
            <span className="field-l">Thesis notes (optional)</span>
            <input className="input" value={thesis} onChange={(e) => setThesis(e.target.value)} placeholder="Why this setup?" />
          </label>
        </div>
      </section>

      {desk.verdict ? (
        <section className="card" aria-label="Validation verdict">
          <div className="card-hd">
            <h2 className="card-title">Verdict</h2>
            <span className={`badge b-${verdictTone}`}>{desk.verdict.decision}</span>
            <span className="card-meta num">
              {desk.verdict.symbol}
              {desk.verdict.score !== null ? ` · score ${desk.verdict.score}` : ''}
              {desk.verdict.riskReward !== null ? ` · R:R ${desk.verdict.riskReward.toFixed(2)}` : ''}
            </span>
          </div>
          <div className="card-bd">
            <CopilotAnswer raw={desk.verdict.verdict} providerLabel={desk.verdict.provider} />
            <div className="sg-kvlist">
              <KvClamped label="technical" value={desk.verdict.technical} />
              <KvClamped label="derivatives" value={desk.verdict.derivatives} />
              <KvClamped label="volatility" value={desk.verdict.volatility} />
              <div className="sg-kv">
                <span className="l">provider</span>
                <span className="v">{desk.verdict.provider}</span>
              </div>
            </div>
            <CappedBullets label="Invalidation" items={desk.verdict.invalidations} />
            <CappedBullets label="Traps" items={desk.verdict.warnings} />
          </div>
        </section>
      ) : null}

      <section className="card" aria-label="Strategy recommendation">
        <div className="card-hd">
          <h2 className="card-title">Strategy architect</h2>
          <span className="card-meta">POST /strategy/recommend</span>
        </div>
        <div className="card-bd">
          <div className="ds-filters">
            <label className="field">
              <span className="field-l">Outlook</span>
              <select className="input" value={outlook} onChange={(e) => setOutlook(e.target.value as typeof outlook)}>
                {OUTLOOKS.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            </label>
            <span className="seg" title="Risk tolerance">
              {RISKS.map((r) => (
                <button key={r} type="button" className="seg-btn" data-active={risk === r} onClick={() => setRisk(r)}>
                  {r}
                </button>
              ))}
            </span>
            <button type="button" className="btn btn-primary" disabled={desk.busy === 'strategy'} onClick={() => void handleStrategy()}>
              {desk.busy === 'strategy' ? 'Recommending… (up to 180s)' : 'Recommend'}
            </button>
          </div>
          <label className="field">
            <span className="field-l">Custom query (optional)</span>
            <input className="input" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. defined-risk bullish, 7 DTE" />
          </label>
        </div>
      </section>

      {desk.strategy ? (
        <section className="card" aria-label="Recommended strategy">
          <div className="card-hd">
            <h2 className="card-title">{desk.strategy.name}</h2>
            <span className="card-meta num">
              {desk.strategy.symbol} · {desk.strategy.outlook}
            </span>
          </div>
          <div className="card-bd">
            <CopilotAnswer raw={desk.strategy.rationale} />
            {desk.strategy.legs.length > 0 ? (
              <div className="tbl-scroll">
                <table className="sg-table">
                  <thead>
                    <tr>
                      <th>Strike</th>
                      <th>Type</th>
                      <th>Action</th>
                      <th>Premium</th>
                    </tr>
                  </thead>
                  <tbody>
                    {desk.strategy.legs.map((leg, i) => (
                      <tr key={i}>
                        <td className="num">{leg.strike}</td>
                        <td>
                          <span className={`sg-tag ${biasTone(leg.type === 'CE' ? 'BULL' : 'BEAR')}`}>{leg.type}</span>
                        </td>
                        <td>{leg.action}</td>
                        <td className="num">{leg.premium}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            <div className="sg-kvlist">
              <div className="sg-kv">
                <span className="l">max profit</span>
                <span className="v">{desk.strategy.maxProfit}</span>
              </div>
              <div className="sg-kv">
                <span className="l">max loss</span>
                <span className="v">{desk.strategy.maxLoss}</span>
              </div>
              <div className="sg-kv">
                <span className="l">risk:reward</span>
                <span className="v">{desk.strategy.riskReward}</span>
              </div>
              <div className="sg-kv">
                <span className="l">breakevens</span>
                <span className="v num">{desk.strategy.breakevens.join(', ') || '—'}</span>
              </div>
            </div>
            {desk.strategy.entry.length > 0 ? <CappedBullets label="Entry" items={desk.strategy.entry} /> : null}
            {desk.strategy.exit.length > 0 ? <CappedBullets label="Exit" items={desk.strategy.exit} /> : null}
            <RiskClamped text={desk.strategy.risk} />
          </div>
        </section>
      ) : null}

      <section className="card" aria-label="Backend check">
        <div className="card-hd">
          <h2 className="card-title">Backend check</h2>
          <span className="card-meta">POST /test</span>
        </div>
        <div className="card-bd">
          <div className="ds-filters">
            <button type="button" className="btn" disabled={desk.busy === 'test'} onClick={() => void handleTest()}>
              {desk.busy === 'test' ? 'Testing… (up to 180s)' : 'Run provider test'}
            </button>
            {desk.testResult ? (
              <span className="stat-chips">
                <span className="stat-chip">
                  <b>{desk.testResult.success ? 'PASS' : 'FAIL'}</b>
                </span>
                <span className="stat-chip">
                  {desk.testResult.provider}
                  {desk.testResult.model ? ` · ${desk.testResult.model}` : ''}
                  {desk.testResult.latencyMs !== null ? ` · ${desk.testResult.latencyMs}ms` : ''}
                </span>
              </span>
            ) : null}
          </div>
          {desk.testResult?.detail ? <p className="sg-note">{desk.testResult.detail}</p> : null}
        </div>
      </section>

      {desk.error ? (
        <div>
          <p className="sg-err">{desk.error}</p>
          <p className="sg-note">{copilotErrorHint(desk.error).hint}</p>
        </div>
      ) : null}
    </div>
  );
}

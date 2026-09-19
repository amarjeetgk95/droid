'use client';

import { useMemo, useState } from 'react';
import { Play, Plus, Trash2 } from 'lucide-react';
import { Card } from '@/components/ui/desk';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/toast';
import { toNumber } from '@/lib/coerce';
import { getObj, pickNum, pickStr } from '@/lib/signalsNormalize';
import { safeNum, safeStr } from '@/lib/utils';
import type { OptionsDeskState } from '@/hooks/useOptionsDesk';
import type { BuiltTemplateStrategy, StrategyLegInput } from '@/lib/api/strategy';
import { payoffStats } from '@/lib/optionsDesk';
import { ResultKV } from './QuantToolsPanel';

function researchBadge(status: unknown): string {
  const s = String(status ?? '').toUpperCase();
  if (s === 'COMPLETE') return 'b-bull';
  if (s === 'PARTIAL' || s === 'FALLBACK_TIMEOUT') return 'b-warn';
  return 'b-neut';
}

function ResearchCard({ desk }: { desk: OptionsDeskState }) {
  const { push } = useToast();
  const [horizon, setHorizon] = useState('INTRADAY');
  const [direction, setDirection] = useState<'BULLISH' | 'BEARISH'>('BULLISH');
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const research = desk.research;

  const handleSynthesize = async () => {
    setBusy(true);
    try {
      const outcome = await desk.synthesizeResearch({ horizon, direction });
      push(outcome.ok ? 'success' : 'error', outcome.message);
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  };

  const evidence = Array.isArray(research?.supporting_evidence) ? research?.supporting_evidence : [];
  const catalysts = Array.isArray(research?.key_catalysts) ? (research?.key_catalysts as unknown[]) : [];

  return (
    <Card title="Financial research" meta={desk.instrument}>
      {!research ? (
        <p className="sg-empty">
          No stored research for {desk.instrument}. Synthesize a fresh report on demand — model
          inference runs server-side and can take a minute.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          <div>
            <span className={`badge ${researchBadge(research.research_status)}`}>
              {String(research.research_status ?? 'UNKNOWN').replace(/_/g, ' ')}
            </span>{' '}
            <span className="card-meta">
              {String(research.proposed_direction ?? '—')} · {String(research.horizon ?? '—')}
            </span>{' '}
            <span className="card-meta">uncertainty {String(research.uncertainty_level ?? '—')}</span>
          </div>
          <div className="sg-kvlist">
            {(
              [
                ['Market', research.market_context],
                ['Macro', research.macro_context],
                ['Fundamental', research.fundamental_context],
                ['News', research.news_context],
                ['Sentiment', research.sentiment_context],
                ['Cross asset', research.cross_asset_context],
                ['AI impact', research.ai_impact],
              ] as Array<[string, unknown]>
            ).map(([label, value]) => (
              <div key={label} className="sg-kv">
                <span className="l">{label}</span>
                <span className="v">{typeof value === 'string' && value ? value : '—'}</span>
              </div>
            ))}
          </div>
          {typeof research.research_assessment === 'string' ? (
            <p className="sg-note">{research.research_assessment}</p>
          ) : null}
          {typeof research.bull_case_summary === 'string' ? (
            <p className="sg-note">Bull case: {research.bull_case_summary}</p>
          ) : null}
          {typeof research.bear_case_summary === 'string' ? (
            <p className="sg-note">Bear case: {research.bear_case_summary}</p>
          ) : null}
          {catalysts.length > 0 ? (
            <div>
              <p className="sg-note">Key catalysts</p>
              {catalysts
                .filter((c): c is string => typeof c === 'string')
                .slice(0, 5)
                .map((catalyst, index) => (
                  <p key={index} className="sg-note">
                    · {catalyst}
                  </p>
                ))}
            </div>
          ) : null}
          {evidence.length > 0 ? (
            <div>
              <p className="sg-note">Supporting evidence</p>
              {evidence.slice(0, 4).map((entry, index) => {
                const o = getObj(entry);
                if (!o) return null;
                return (
                  <p key={index} className="sg-note">
                    · {pickStr(o, 'claim') ?? '—'}
                    {pickStr(o, 'source_name') ? ` — ${pickStr(o, 'source_name')}` : ''}
                  </p>
                );
              })}
            </div>
          ) : null}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <span className="sg-lab">
          <span>Horizon</span>
          <span className="seg">
            {['SCALP', 'INTRADAY', 'SWING'].map((h) => (
              <button key={h} type="button" className="seg-btn" data-active={horizon === h} onClick={() => setHorizon(h)}>
                {h}
              </button>
            ))}
          </span>
        </span>
        <span className="sg-lab">
          <span>Direction</span>
          <span className="seg">
            {(['BULLISH', 'BEARISH'] as const).map((d) => (
              <button key={d} type="button" className="seg-btn" data-active={direction === d} onClick={() => setDirection(d)}>
                {d}
              </button>
            ))}
          </span>
        </span>
        <button type="button" className="btn btn-primary" disabled={busy} onClick={() => setConfirming(true)}>
          {busy ? 'Synthesizing…' : 'Synthesize fresh research'}
        </button>
      </div>
      <ConfirmDialog
        open={confirming}
        onOpenChange={(open) => {
          if (!open) setConfirming(false);
        }}
        tone="primary"
        confirmLabel="Synthesize research"
        busy={busy}
        title={`Synthesize fresh ${direction} research for ${desk.instrument}?`}
        description="Runs model inference server-side (up to a few minutes). The stored report is replaced on success."
        intentRows={[
          { label: 'Underlying', value: desk.instrument },
          { label: 'Horizon', value: horizon },
          { label: 'Direction', value: direction },
        ]}
        onConfirm={handleSynthesize}
      />
    </Card>
  );
}

function TemplatesCard({ desk }: { desk: OptionsDeskState }) {
  const { push } = useToast();
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [built, setBuilt] = useState<BuiltTemplateStrategy | null>(null);

  const pending = useMemo(
    () => desk.templates.find((t) => t.id === pendingId) ?? null,
    [desk.templates, pendingId],
  );

  const handleBuild = async () => {
    if (!pendingId) return;
    setBusy(true);
    try {
      const outcome = await desk.buildTemplate(pendingId);
      push(outcome.ok ? 'success' : 'error', outcome.message);
      if (outcome.ok) setBuilt(outcome.strategy);
    } finally {
      setBusy(false);
      setPendingId(null);
    }
  };

  const stats = useMemo(() => payoffStats(built?.payoff_curve), [built]);

  return (
    <Card title="Strategy templates" meta={`${desk.templates.length} templates`}>
      {desk.templates.length === 0 ? (
        <p className="sg-empty">No strategy templates published by the backend.</p>
      ) : (
        <div className="tbl-scroll">
          <table className="sg-table">
            <thead>
              <tr>
                <th>Template</th>
                <th>Category</th>
                <th className="r">Legs</th>
                <th className="r">Build</th>
              </tr>
            </thead>
            <tbody>
              {desk.templates.map((template) => (
                <tr key={template.id}>
                  <td>
                    <div className="sg-sym">{template.name}</div>
                    <div className="sg-rownote">{template.description}</div>
                  </td>
                  <td>
                    <span className="sg-tag neut">{template.category.replace(/_/g, ' ')}</span>
                  </td>
                  <td className="r num">{template.legs_count}</td>
                  <td>
                    <div className="sg-actions">
                      <button
                        type="button"
                        className="sg-ibtn"
                        title={`Build ${template.name} off the live ${desk.instrument} spot`}
                        onClick={() => setPendingId(template.id)}
                      >
                        <Play size={12} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {built ? (
        <div className="flex flex-col gap-3">
          <p className="sg-note">
            Built {built.template_id} off live spot {safeNum(built.spot_price)} — {built.legs.length} leg(s).
            Max profit {safeNum(built.max_profit, '—', 0)} · max loss {safeNum(built.max_loss, '—', 0)} ·
            R/R {built.risk_reward !== null ? safeNum(built.risk_reward) : '—'} · breakevens{' '}
            {stats.breakevens.length > 0 ? stats.breakevens.map((b) => safeNum(b, '—', 0)).join(' / ') : '—'}.
          </p>
          <p className="sg-note">{safeStr(built.premium_note, '')}</p>
          <div className="tbl-scroll">
            <table className="sg-table">
              <thead>
                <tr>
                  <th>Leg</th>
                  <th>Side</th>
                  <th className="r">Strike</th>
                  <th className="r">Qty</th>
                  <th className="r">Est. premium</th>
                </tr>
              </thead>
              <tbody>
                {built.legs.map((leg, index) => (
                  <tr key={leg.id ?? index}>
                    <td className="sg-sym">{leg.option_type}</td>
                    <td>
                      <span className={`sg-dir ${leg.side === 'BUY' ? 'long' : leg.side === 'SELL' ? 'short' : ''}`}>
                        {leg.side || '—'}
                      </span>
                    </td>
                    <td className="r num">{safeNum(leg.strike, '—', 1)}</td>
                    <td className="r num">{leg.quantity}</td>
                    <td className="r num">{safeNum(leg.price)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(open) => {
          if (!open) setPendingId(null);
        }}
        tone="primary"
        confirmLabel="Build off live spot"
        busy={busy}
        title={`Build ${pending?.name ?? 'template'} for ${desk.instrument}?`}
        description="Reads the live spot and shapes estimation premiums into a payoff curve. Replace premiums with live chain quotes before trading."
        intentRows={
          pending
            ? [
                { label: 'Template', value: pending.name },
                { label: 'Underlying', value: desk.instrument },
                { label: 'Legs', value: String(pending.legs_count) },
              ]
            : undefined
        }
        onConfirm={handleBuild}
      />
    </Card>
  );
}

type EditableLeg = {
  key: number;
  option_type: 'CE' | 'PE';
  side: 'BUY' | 'SELL';
  strike: string;
  quantity: string;
  price: string;
};

let legKey = 1;

function PayoffCard({ desk, spot }: { desk: OptionsDeskState; spot: number | null }) {
  const { push } = useToast();
  const [legs, setLegs] = useState<EditableLeg[]>([
    { key: legKey++, option_type: 'CE', side: 'BUY', strike: '', quantity: '1', price: '' },
    { key: legKey++, option_type: 'CE', side: 'SELL', strike: '', quantity: '1', price: '' },
  ]);
  const [spotText, setSpotText] = useState('');
  const [busy, setBusy] = useState(false);
  const [curve, setCurve] = useState<Array<{ spot: number; pnl: number }> | null>(null);

  const stats = useMemo(() => payoffStats(curve), [curve]);

  const updateLeg = (key: number, patch: Partial<EditableLeg>) => {
    setLegs((prev) => prev.map((leg) => (leg.key === key ? { ...leg, ...patch } : leg)));
  };

  const submit = async () => {
    const spotNum = toNumber(spotText, { rejectBlankString: true }) ?? spot;
    if (spotNum === null) {
      push('error', 'Spot is required — enter one or wait for the chain to load.');
      return;
    }
    const parsed: StrategyLegInput[] = [];
    for (const leg of legs) {
      const strikeNum = toNumber(leg.strike, { rejectBlankString: true });
      const qtyNum = toNumber(leg.quantity, { rejectBlankString: true });
      const priceNum = toNumber(leg.price, { rejectBlankString: true });
      if (strikeNum === null || qtyNum === null || priceNum === null) {
        push('error', 'Every leg needs a strike, quantity and premium.');
        return;
      }
      parsed.push({
        option_type: leg.option_type,
        side: leg.side,
        strike: strikeNum,
        quantity: Math.round(qtyNum),
        price: priceNum,
      });
    }
    if (parsed.length === 0) {
      push('error', 'Add at least one leg.');
      return;
    }
    setBusy(true);
    try {
      const outcome = await desk.calcPayoff({ underlying: desk.instrument, spot_price: spotNum, legs: parsed });
      push(outcome.ok ? 'success' : 'error', outcome.message);
      const data = getObj(outcome.value);
      const rawCurve = data && Array.isArray(data.payoff_curve) ? data.payoff_curve : null;
      setCurve(
        rawCurve
          ? rawCurve
              .map((entry) => {
                const o = getObj(entry);
                if (!o) return null;
                const s = pickNum(o, 'spot');
                const p = pickNum(o, 'pnl');
                return s !== null && p !== null ? { spot: s, pnl: p } : null;
              })
              .filter((p): p is { spot: number; pnl: number } => p !== null)
          : null,
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Payoff viewer" meta={desk.instrument}>
      <div className="flex flex-wrap items-center gap-2">
        <label className="field">
          <span className="field-l">Spot (chain {spot !== null ? safeNum(spot) : 'n/a'})</span>
          <input
            className="input num"
            type="number"
            value={spotText}
            onChange={(e) => setSpotText(e.target.value)}
            placeholder={spot !== null ? safeNum(spot) : ''}
          />
        </label>
        <button
          type="button"
          className="btn btn-ic"
          onClick={() =>
            setLegs((prev) => [
              ...prev,
              { key: legKey++, option_type: 'CE', side: 'BUY', strike: '', quantity: '1', price: '' },
            ])
          }
        >
          <Plus size={13} />
          Add leg
        </button>
        <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void submit()}>
          {busy ? 'Calculating…' : 'Calculate payoff'}
        </button>
      </div>
      <div className="tbl-scroll">
        <table className="sg-table">
          <thead>
            <tr>
              <th>Type</th>
              <th>Side</th>
              <th className="r">Strike</th>
              <th className="r">Qty</th>
              <th className="r">Premium</th>
              <th className="r">Remove</th>
            </tr>
          </thead>
          <tbody>
            {legs.map((leg) => (
              <tr key={leg.key}>
                <td>
                  <span className="seg">
                    {(['CE', 'PE'] as const).map((t) => (
                      <button
                        key={t}
                        type="button"
                        className="seg-btn"
                        data-active={leg.option_type === t}
                        onClick={() => updateLeg(leg.key, { option_type: t })}
                      >
                        {t}
                      </button>
                    ))}
                  </span>
                </td>
                <td>
                  <span className="seg">
                    {(['BUY', 'SELL'] as const).map((s) => (
                      <button
                        key={s}
                        type="button"
                        className="seg-btn"
                        data-active={leg.side === s}
                        onClick={() => updateLeg(leg.key, { side: s })}
                      >
                        {s}
                      </button>
                    ))}
                  </span>
                </td>
                <td className="r">
                  <input
                    className="input num"
                    type="number"
                    value={leg.strike}
                    onChange={(e) => updateLeg(leg.key, { strike: e.target.value })}
                    placeholder="23350"
                    aria-label="Leg strike"
                  />
                </td>
                <td className="r">
                  <input
                    className="input num"
                    type="number"
                    value={leg.quantity}
                    onChange={(e) => updateLeg(leg.key, { quantity: e.target.value })}
                    placeholder="1"
                    aria-label="Leg quantity"
                  />
                </td>
                <td className="r">
                  <input
                    className="input num"
                    type="number"
                    value={leg.price}
                    onChange={(e) => updateLeg(leg.key, { price: e.target.value })}
                    placeholder="133.07"
                    aria-label="Leg premium"
                  />
                </td>
                <td>
                  <div className="sg-actions">
                    <button
                      type="button"
                      className="sg-ibtn danger"
                      title="Remove leg"
                      disabled={legs.length <= 1}
                      onClick={() => setLegs((prev) => prev.filter((l) => l.key !== leg.key))}
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {curve ? (
        <div className="flex flex-col gap-3">
          <p className="sg-note">
            Max profit {stats.maxProfit !== null ? safeNum(stats.maxProfit, '—', 0) : '—'} · max loss{' '}
            {stats.maxLoss !== null ? safeNum(stats.maxLoss, '—', 0) : '—'} · breakevens{' '}
            {stats.breakevens.length > 0 ? stats.breakevens.map((b) => safeNum(b, '—', 0)).join(' / ') : '—'} (
            {stats.points} points).
          </p>
          <div className="tbl-scroll">
            <table className="sg-table">
              <thead>
                <tr>
                  <th className="r">Spot</th>
                  <th className="r">P&amp;L</th>
                </tr>
              </thead>
              <tbody>
                {curve.map((point, index) => (
                  <tr key={index}>
                    <td className="r num">{safeNum(point.spot)}</td>
                    <td className="r num">{safeNum(point.pnl, '—', 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <p className="sg-note">Pure expiry payoff math over your legs — no market data is consumed.</p>
      )}
    </Card>
  );
}

function ScannerCard({ desk }: { desk: OptionsDeskState }) {
  const scans = Array.isArray(desk.scanner?.scans) ? desk.scanner?.scans : [];
  return (
    <Card title="Strategy scanner" meta={`${scans.length} scans`}>
      {scans.length === 0 ? (
        <p className="sg-empty">
          {safeStr(desk.scanner?.limitation, 'No strategy recommendations right now — the scanner only publishes live-analytics-backed ideas.')}
        </p>
      ) : (
        <div className="tbl-scroll">
          <table className="sg-table">
            <thead>
              <tr>
                <th>Scan</th>
                <th className="r">Detail</th>
              </tr>
            </thead>
            <tbody>
              {scans.map((entry, index) => {
                const o = getObj(entry);
                return (
                  <tr key={index}>
                    <td className="sg-sym">{(o && pickStr(o, 'name', 'strategy', 'id')) ?? `scan ${index + 1}`}</td>
                    <td className="r sg-rownote">{o ? JSON.stringify(o).slice(0, 120) : '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function GreeksLedgerCard({ desk }: { desk: OptionsDeskState }) {
  const g = desk.portfolioGreeks;
  if (!g) {
    return (
      <Card title="Portfolio Greeks">
        <p className="sg-empty">Greeks ledger unavailable.</p>
      </Card>
    );
  }
  if ((g.total_open_positions ?? 0) === 0) {
    return (
      <Card title="Portfolio Greeks" meta="0 open">
        <p className="sg-empty">No open positions in the Greeks ledger — net and gross exposure are both zero.</p>
      </Card>
    );
  }
  const exposureRows = (record: Record<string, number> | undefined): Array<[string, number]> =>
    record ? Object.entries(record) : [];
  return (
    <Card title="Portfolio Greeks" meta={`${g.total_open_positions} open`}>
      <div className="sg-kvlist">
        <div className="sg-kv"><span className="l">Net Δ / gross Δ</span><span className="v">{safeNum(g.total_delta)} / {safeNum(g.gross_delta)}</span></div>
        <div className="sg-kv"><span className="l">Net Γ / gross Γ</span><span className="v">{safeNum(g.total_gamma)} / {safeNum(g.gross_gamma)}</span></div>
        <div className="sg-kv"><span className="l">Net Θ/day / gross</span><span className="v">{safeNum(g.total_theta_day)} / {safeNum(g.gross_theta_day)}</span></div>
        <div className="sg-kv"><span className="l">Net vega / gross</span><span className="v">{safeNum(g.total_vega)} / {safeNum(g.gross_vega)}</span></div>
        {exposureRows(g.net_exposure_by_underlying).map(([underlying, value]) => (
          <div key={underlying} className="sg-kv"><span className="l">Net {underlying}</span><span className="v">{safeNum(value)}</span></div>
        ))}
        {exposureRows(g.positions_by_horizon).map(([horizon, count]) => (
          <div key={horizon} className="sg-kv"><span className="l">Positions {horizon}</span><span className="v">{safeNum(count, '—', 0)}</span></div>
        ))}
      </div>
      <ResultKV value={g.expiry_concentrations ?? {}} />
    </Card>
  );
}

export function StrategyPanel({ desk, spot }: { desk: OptionsDeskState; spot: number | null }) {
  return (
    <div className="flex flex-col gap-3">
      <p className="sg-note">
        Templates build off the live spot (confirm first — premiums are estimation inputs, never
        market quotes). The payoff viewer is pure math over your legs. The scanner stays empty
        until live analytics wire it.
      </p>
      <ResearchCard desk={desk} />
      <TemplatesCard desk={desk} />
      <PayoffCard desk={desk} spot={spot} />
      <ScannerCard desk={desk} />
      <GreeksLedgerCard desk={desk} />
    </div>
  );
}

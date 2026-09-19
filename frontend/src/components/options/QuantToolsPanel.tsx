'use client';

import { useState } from 'react';
import { Calculator } from 'lucide-react';
import { Card } from '@/components/ui/desk';
import { useToast } from '@/components/ui/toast';
import { toNumber } from '@/lib/coerce';
import { getObj, pickNum, pickStr } from '@/lib/signalsNormalize';
import { safeNum } from '@/lib/utils';
import type { OptionsDeskState } from '@/hooks/useOptionsDesk';

function parseNum(text: string): number | null {
  return toNumber(text, { rejectBlankString: true });
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="field">
      <span className="field-l">{label}</span>
      {children}
    </label>
  );
}

/** Honest scalar dump of a tool result — no invented keys, no hidden objects. */
export function ResultKV({ value, exclude }: { value: Record<string, unknown>; exclude?: string[] }) {
  const rows = Object.entries(value).filter(
    ([key, v]) =>
      !(exclude ?? []).includes(key) &&
      (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean'),
  );
  if (rows.length === 0) return null;
  return (
    <div className="sg-kvlist">
      {rows.map(([key, v]) => (
        <div key={key} className="sg-kv">
          <span className="l">{key.replace(/_/g, ' ')}</span>
          <span className="v">
            {typeof v === 'number' ? safeNum(v) : typeof v === 'boolean' ? (v ? 'YES' : 'NO') : String(v)}
          </span>
        </div>
      ))}
    </div>
  );
}

function Rationale({ items }: { items: unknown }) {
  if (!Array.isArray(items) || items.length === 0) return null;
  const lines = items.filter((i): i is string => typeof i === 'string' && i.length > 0);
  if (lines.length === 0) return null;
  return (
    <div className="flex flex-col gap-3">
      {lines.map((line, index) => (
        <p key={index} className="sg-note">
          {line}
        </p>
      ))}
    </div>
  );
}

type OptionType = 'CE' | 'PE';

function GreeksForm({ desk, spot, atm }: { desk: OptionsDeskState; spot: number | null; atm: number | null }) {
  const { push } = useToast();
  const [strike, setStrike] = useState('');
  const [dte, setDte] = useState('');
  const [vol, setVol] = useState('');
  const [optionType, setOptionType] = useState<OptionType>('CE');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const submit = async () => {
    const strikeNum = parseNum(strike) ?? atm;
    const dteNum = parseNum(dte);
    const volPct = parseNum(vol);
    if (spot === null || strikeNum === null || dteNum === null || volPct === null) {
      push('error', 'Spot, strike, DTE and volatility (IV %) are all required.');
      return;
    }
    setBusy(true);
    try {
      const outcome = await desk.calcGreeks({
        spot,
        strike: strikeNum,
        dte_days: dteNum,
        volatility: volPct / 100,
        option_type: optionType,
      });
      push(outcome.ok ? 'success' : 'error', outcome.message);
      setResult(outcome.value);
    } finally {
      setBusy(false);
    }
  };

  const moneyness = result
    ? result.is_atm === true
      ? 'ATM'
      : result.is_itm === true
        ? 'ITM'
        : result.is_otm === true
          ? 'OTM'
          : null
    : null;

  return (
    <Card title="Greeks calculator" meta={desk.instrument}>
      <div className="flex flex-wrap items-center gap-2">
        <Field label={`Spot (chain ${spot !== null ? safeNum(spot) : 'n/a'})`}>
          <input className="input num" value={spot !== null ? safeNum(spot) : ''} disabled placeholder="chain spot" />
        </Field>
        <Field label={`Strike (ATM ${atm !== null ? safeNum(atm, '—', 0) : 'n/a'})`}>
          <input className="input num" type="number" value={strike} onChange={(e) => setStrike(e.target.value)} placeholder={atm !== null ? String(Math.round(atm)) : ''} />
        </Field>
        <Field label="DTE (days)">
          <input className="input num" type="number" value={dte} onChange={(e) => setDte(e.target.value)} placeholder="3.5" />
        </Field>
        <Field label="Volatility (IV %)">
          <input className="input num" type="number" value={vol} onChange={(e) => setVol(e.target.value)} placeholder="12" />
        </Field>
        <span className="sg-lab">
          <span>Type</span>
          <span className="seg">
            {(['CE', 'PE'] as OptionType[]).map((t) => (
              <button key={t} type="button" className="seg-btn" data-active={optionType === t} onClick={() => setOptionType(t)}>
                {t}
              </button>
            ))}
          </span>
        </span>
        <button type="button" className="btn btn-primary btn-ic" disabled={busy} onClick={() => void submit()}>
          <Calculator size={13} />
          {busy ? 'Pricing…' : 'Price & Greeks'}
        </button>
      </div>
      {result ? (
        <div className="flex flex-col gap-3">
          <div>
            {moneyness ? <span className="sg-tag info">{moneyness}</span> : null}{' '}
            <span className="card-meta num">IV {safeNum(pickNum(result, 'iv') !== null ? (pickNum(result, 'iv') as number) * 100 : null)}%</span>
          </div>
          <div className="sg-kvlist">
            <div className="sg-kv"><span className="l">Theoretical price</span><span className="v">{safeNum(pickNum(result, 'theoretical_price'))}</span></div>
            <div className="sg-kv"><span className="l">Delta</span><span className="v">{safeNum(pickNum(result, 'delta'))}</span></div>
            <div className="sg-kv"><span className="l">Gamma</span><span className="v">{safeNum(pickNum(result, 'gamma'))}</span></div>
            <div className="sg-kv"><span className="l">Theta / day</span><span className="v">{safeNum(pickNum(result, 'theta_day'))}</span></div>
            <div className="sg-kv"><span className="l">Theta / hour</span><span className="v">{safeNum(pickNum(result, 'theta_hour'))}</span></div>
            <div className="sg-kv"><span className="l">Vega</span><span className="v">{safeNum(pickNum(result, 'vega'))}</span></div>
            <div className="sg-kv"><span className="l">Rho</span><span className="v">{safeNum(pickNum(result, 'rho'))}</span></div>
            <div className="sg-kv"><span className="l">Moneyness</span><span className="v">{safeNum(pickNum(result, 'moneyness'))}</span></div>
          </div>
        </div>
      ) : (
        <p className="sg-note">Pure Black-Scholes math — no chain state is touched.</p>
      )}
    </Card>
  );
}

function IvForm({ desk, spot, atm }: { desk: OptionsDeskState; spot: number | null; atm: number | null }) {
  const { push } = useToast();
  const [price, setPrice] = useState('');
  const [strike, setStrike] = useState('');
  const [dte, setDte] = useState('');
  const [optionType, setOptionType] = useState<OptionType>('CE');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const submit = async () => {
    const priceNum = parseNum(price);
    const strikeNum = parseNum(strike) ?? atm;
    const dteNum = parseNum(dte);
    if (spot === null || priceNum === null || strikeNum === null || dteNum === null) {
      push('error', 'Market price, strike and DTE are required (spot comes from the chain).');
      return;
    }
    setBusy(true);
    try {
      const outcome = await desk.solveIv({
        market_price: priceNum,
        spot,
        strike: strikeNum,
        dte_days: dteNum,
        option_type: optionType,
      });
      push(outcome.ok ? 'success' : 'error', outcome.message);
      setResult(outcome.value);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="IV solver" meta={desk.instrument}>
      <div className="flex flex-wrap items-center gap-2">
        <Field label="Market premium">
          <input className="input num" type="number" value={price} onChange={(e) => setPrice(e.target.value)} placeholder="115" />
        </Field>
        <Field label="Strike">
          <input className="input num" type="number" value={strike} onChange={(e) => setStrike(e.target.value)} placeholder={atm !== null ? String(Math.round(atm)) : ''} />
        </Field>
        <Field label="DTE (days)">
          <input className="input num" type="number" value={dte} onChange={(e) => setDte(e.target.value)} placeholder="3.5" />
        </Field>
        <span className="sg-lab">
          <span>Type</span>
          <span className="seg">
            {(['CE', 'PE'] as OptionType[]).map((t) => (
              <button key={t} type="button" className="seg-btn" data-active={optionType === t} onClick={() => setOptionType(t)}>
                {t}
              </button>
            ))}
          </span>
        </span>
        <button type="button" className="btn btn-primary btn-ic" disabled={busy} onClick={() => void submit()}>
          <Calculator size={13} />
          {busy ? 'Solving…' : 'Solve IV'}
        </button>
      </div>
      {result ? (
        <div className="sg-kvlist">
          <div className="sg-kv"><span className="l">Implied volatility</span><span className="v">{safeNum(pickNum(result, 'iv_percent'), '—', 2)}%</span></div>
          <div className="sg-kv"><span className="l">IV (decimal)</span><span className="v">{safeNum(pickNum(result, 'implied_volatility'))}</span></div>
        </div>
      ) : (
        <p className="sg-note">Inverts the market premium into an annualized volatility.</p>
      )}
    </Card>
  );
}

const SIM_SCENARIOS = [
  'fast_target',
  'slow_target',
  'sideways',
  'adverse_stop',
  'pin_expiry',
  'time_stop_exit',
  'iv_crush_target',
] as const;

function SimForm({ desk, spot, atm }: { desk: OptionsDeskState; spot: number | null; atm: number | null }) {
  const { push } = useToast();
  const [strike, setStrike] = useState('');
  const [dte, setDte] = useState('');
  const [iv, setIv] = useState('');
  const [target, setTarget] = useState('');
  const [stop, setStop] = useState('');
  const [qty, setQty] = useState('75');
  const [optionType, setOptionType] = useState<OptionType>('CE');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const submit = async () => {
    const strikeNum = parseNum(strike) ?? atm;
    const dteNum = parseNum(dte);
    const ivNum = parseNum(iv);
    const targetNum = parseNum(target);
    const stopNum = parseNum(stop);
    const qtyNum = parseNum(qty);
    if (spot === null || strikeNum === null || dteNum === null || ivNum === null || targetNum === null || stopNum === null || qtyNum === null) {
      push('error', 'Strike, DTE, IV %, target, stop and quantity are all required.');
      return;
    }
    setBusy(true);
    try {
      const outcome = await desk.simulatePath({
        underlying: desk.instrument,
        spot,
        strike: strikeNum,
        option_type: optionType,
        dte_days: dteNum,
        iv: ivNum / 100,
        target_spot: targetNum,
        stop_spot: stopNum,
        quantity: Math.round(qtyNum),
      });
      push(outcome.ok ? 'success' : 'error', outcome.message);
      setResult(outcome.value);
    } finally {
      setBusy(false);
    }
  };

  const viable = result?.is_economically_viable;

  return (
    <Card title="Path simulator" meta={desk.instrument}>
      <div className="flex flex-wrap items-center gap-2">
        <Field label="Strike">
          <input className="input num" type="number" value={strike} onChange={(e) => setStrike(e.target.value)} placeholder={atm !== null ? String(Math.round(atm)) : ''} />
        </Field>
        <Field label="DTE (days)">
          <input className="input num" type="number" value={dte} onChange={(e) => setDte(e.target.value)} placeholder="3.5" />
        </Field>
        <Field label="IV %">
          <input className="input num" type="number" value={iv} onChange={(e) => setIv(e.target.value)} placeholder="12" />
        </Field>
        <Field label="Target spot">
          <input className="input num" type="number" value={target} onChange={(e) => setTarget(e.target.value)} placeholder="23450" />
        </Field>
        <Field label="Stop spot">
          <input className="input num" type="number" value={stop} onChange={(e) => setStop(e.target.value)} placeholder="23250" />
        </Field>
        <Field label="Quantity">
          <input className="input num" type="number" value={qty} onChange={(e) => setQty(e.target.value)} placeholder="75" />
        </Field>
        <span className="sg-lab">
          <span>Type</span>
          <span className="seg">
            {(['CE', 'PE'] as OptionType[]).map((t) => (
              <button key={t} type="button" className="seg-btn" data-active={optionType === t} onClick={() => setOptionType(t)}>
                {t}
              </button>
            ))}
          </span>
        </span>
        <button type="button" className="btn btn-primary btn-ic" disabled={busy} onClick={() => void submit()}>
          <Calculator size={13} />
          {busy ? 'Simulating…' : 'Simulate paths'}
        </button>
      </div>
      {result ? (
        <div className="flex flex-col gap-3">
          <div>
            <span className={`badge ${viable === true ? 'b-bull' : viable === false ? 'b-bear' : 'b-neut'}`}>
              {viable === true ? 'ECONOMICALLY VIABLE' : viable === false ? 'NOT VIABLE' : 'VIABILITY UNKNOWN'}
            </span>{' '}
            <span className="card-meta num">entry {safeNum(pickNum(result, 'entry_premium'))}</span>
          </div>
          <Rationale items={result.viability_rationale} />
          {SIM_SCENARIOS.map((key) => {
            const scenario = getObj(result[key]);
            if (!scenario) return null;
            return (
              <div key={key}>
                <p className="sg-note">{key.replace(/_/g, ' ')}</p>
                <ResultKV value={scenario} />
              </div>
            );
          })}
        </div>
      ) : (
        <p className="sg-note">Five path scenarios with statutory friction — pure math, no order is placed.</p>
      )}
    </Card>
  );
}

function ExpectedMoveForm({ desk, spot }: { desk: OptionsDeskState; spot: number | null }) {
  const { push } = useToast();
  const [direction, setDirection] = useState<'BULLISH' | 'BEARISH'>('BULLISH');
  const [horizon, setHorizon] = useState('INTRADAY');
  const [iv, setIv] = useState('');
  const [atr, setAtr] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const submit = async () => {
    if (spot === null) {
      push('error', 'Chain spot unavailable — expected move needs a live spot.');
      return;
    }
    setBusy(true);
    try {
      const outcome = await desk.projectExpectedMove({
        underlying: desk.instrument,
        spot,
        direction,
        horizon,
        current_iv: parseNum(iv) !== null ? (parseNum(iv) as number) / 100 : 0.15,
        atr: parseNum(atr),
      });
      push(outcome.ok ? 'success' : 'error', outcome.message);
      setResult(outcome.value);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Expected move" meta={desk.instrument}>
      <div className="flex flex-wrap items-center gap-2">
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
        <Field label="Current IV % (blank 15)">
          <input className="input num" type="number" value={iv} onChange={(e) => setIv(e.target.value)} placeholder="12" />
        </Field>
        <Field label="ATR (optional)">
          <input className="input num" type="number" value={atr} onChange={(e) => setAtr(e.target.value)} placeholder="60" />
        </Field>
        <button type="button" className="btn btn-primary btn-ic" disabled={busy} onClick={() => void submit()}>
          <Calculator size={13} />
          {busy ? 'Projecting…' : 'Project move'}
        </button>
      </div>
      {result ? (
        <div className="flex flex-col gap-3">
          <div className="sg-kvlist">
            <div className="sg-kv"><span className="l">Expected move (pts)</span><span className="v">{safeNum(pickNum(result, 'expected_move_points'))}</span></div>
            <div className="sg-kv"><span className="l">Expected move %</span><span className="v">{safeNum(pickNum(result, 'expected_move_pct'))}</span></div>
            <div className="sg-kv"><span className="l">Conservative / aggressive</span><span className="v">{safeNum(pickNum(result, 'conservative_move_points'))} / {safeNum(pickNum(result, 'aggressive_move_points'))}</span></div>
            <div className="sg-kv"><span className="l">IV 1σ move</span><span className="v">{safeNum(pickNum(result, 'iv_implied_1sigma_move'))}</span></div>
            <div className="sg-kv"><span className="l">Velocity (pts/hr)</span><span className="v">{safeNum(pickNum(result, 'expected_velocity_pts_per_hour'))}</span></div>
            <div className="sg-kv"><span className="l">Fast enough</span><span className="v">{result.is_fast_enough_for_option === true ? 'YES' : result.is_fast_enough_for_option === false ? 'NO' : '—'}</span></div>
            <div className="sg-kv"><span className="l">Calibration confidence</span><span className="v">{safeNum(pickNum(result, 'calibration_confidence'), '—', 1)}%</span></div>
          </div>
          <Rationale items={result.forecast_rationale ?? pickStr(result, 'velocity_assessment')} />
          {typeof result.velocity_assessment === 'string' ? <p className="sg-note">{result.velocity_assessment}</p> : null}
        </div>
      ) : (
        <p className="sg-note">Magnitude, timing and velocity versus option theta.</p>
      )}
    </Card>
  );
}

function SelectorForm({ desk, spot }: { desk: OptionsDeskState; spot: number | null }) {
  const { push } = useToast();
  const [direction, setDirection] = useState<'LONG_CALL' | 'LONG_PUT'>('LONG_CALL');
  const [stopLoss, setStopLoss] = useState('30');
  const [horizonHrs, setHorizonHrs] = useState('1');
  const [iv, setIv] = useState('');
  const [move, setMove] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const submit = async () => {
    if (spot === null) {
      push('error', 'Chain spot unavailable — contract selection needs a live spot.');
      return;
    }
    setBusy(true);
    try {
      const outcome = await desk.selectContract({
        underlying: desk.instrument,
        spot_price: spot,
        direction,
        expected_move_points: parseNum(move),
        stop_loss_points: parseNum(stopLoss) ?? 30,
        target_horizon_hours: parseNum(horizonHrs) ?? 1,
        current_iv: parseNum(iv) !== null ? (parseNum(iv) as number) / 100 : 0.16,
      });
      push(outcome.ok ? 'success' : 'error', outcome.message);
      setResult(outcome.value);
    } finally {
      setBusy(false);
    }
  };

  const candidates = result ? [result.ranked_candidates, result.candidates].find((v) => Array.isArray(v)) : null;

  return (
    <Card title="Contract selector" meta={desk.instrument}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="sg-lab">
          <span>Direction</span>
          <span className="seg">
            {(['LONG_CALL', 'LONG_PUT'] as const).map((d) => (
              <button key={d} type="button" className="seg-btn" data-active={direction === d} onClick={() => setDirection(d)}>
                {d}
              </button>
            ))}
          </span>
        </span>
        <Field label="Stop (pts)">
          <input className="input num" type="number" value={stopLoss} onChange={(e) => setStopLoss(e.target.value)} placeholder="30" />
        </Field>
        <Field label="Horizon (hrs)">
          <input className="input num" type="number" value={horizonHrs} onChange={(e) => setHorizonHrs(e.target.value)} placeholder="1" />
        </Field>
        <Field label="Current IV % (blank 16)">
          <input className="input num" type="number" value={iv} onChange={(e) => setIv(e.target.value)} placeholder="16" />
        </Field>
        <Field label="Expected move (optional)">
          <input className="input num" type="number" value={move} onChange={(e) => setMove(e.target.value)} placeholder="80" />
        </Field>
        <button type="button" className="btn btn-primary btn-ic" disabled={busy} onClick={() => void submit()}>
          <Calculator size={13} />
          {busy ? 'Ranking…' : 'Rank contracts'}
        </button>
      </div>
      {result ? (
        <div className="flex flex-col gap-3">
          <div className="sg-kvlist">
            <div className="sg-kv"><span className="l">Selected strike</span><span className="v">{safeNum(pickNum(result, 'selected_strike', 'strike'), '—', 0)}</span></div>
            <div className="sg-kv"><span className="l">Selected expiry</span><span className="v">{pickStr(result, 'selected_expiry', 'expiry') ?? '—'}</span></div>
            <div className="sg-kv"><span className="l">Score</span><span className="v">{safeNum(pickNum(result, 'selection_score', 'score'))}</span></div>
          </div>
          <ResultKV value={result} exclude={['ranked_candidates', 'candidates', 'rationale', 'selection_rationale']} />
          <Rationale items={result.selection_rationale ?? result.rationale} />
          {Array.isArray(candidates) && candidates.length > 0 ? (
            <div className="tbl-scroll">
              <table className="sg-table">
                <thead>
                  <tr>
                    <th>Candidate</th>
                    <th className="r">Strike</th>
                    <th className="r">Score</th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.slice(0, 6).map((entry, index) => {
                    const row = getObj(entry);
                    if (!row) return null;
                    return (
                      <tr key={index}>
                        <td className="sg-rownote">{pickStr(row, 'contract', 'symbol', 'expiry') ?? `candidate ${index + 1}`}</td>
                        <td className="r num">{safeNum(pickNum(row, 'strike'), '—', 0)}</td>
                        <td className="r num">{safeNum(pickNum(row, 'score', 'selection_score', 'total_score'))}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : (
        <p className="sg-note">
          Ranks ITM / ATM / OTM candidates off live chain quotes — fail-closed when the chain is
          unreachable, so an empty result means no quotable contract, not a silent default.
        </p>
      )}
    </Card>
  );
}

export function QuantToolsPanel({
  desk,
  spot,
  atm,
}: {
  desk: OptionsDeskState;
  spot: number | null;
  atm: number | null;
}) {
  return (
    <div className="flex flex-col gap-3">
      <p className="sg-note">
        On-demand quant tools. Every calculation runs only when you submit its form and reports
        through a toast — nothing here polls or places orders. Spot and ATM prefill from the chain
        ladder above; leave a field blank to fall back to the chain mark where shown.
      </p>
      <GreeksForm desk={desk} spot={spot} atm={atm} />
      <IvForm desk={desk} spot={spot} atm={atm} />
      <SimForm desk={desk} spot={spot} atm={atm} />
      <ExpectedMoveForm desk={desk} spot={spot} />
      <SelectorForm desk={desk} spot={spot} />
    </div>
  );
}

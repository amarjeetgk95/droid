'use client';

/* Signal dossier — institutional detail view for one live or executed signal.
   Sections: decision summary → mechanism (confluence maths) → levels & risk →
   contract → execution & P&L → lifecycle timeline.
   Fetches deep-dive (FSM) + audit (ledger) in parallel; either may 404 and
   the drawer degrades to whatever source survived. */

import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, X } from 'lucide-react';
import { api } from '@/lib/api';
import { fmtINR } from '@/components/ui/desk';
import { normalizeDirection } from '@/components/ui/desk';
import {
  asNum,
  asStr,
  fmtDateTimeMs,
  getObj,
  pickNum,
  pickStr,
  stateTone,
} from './signalsNormalize';

function n(v: unknown): number | null {
  return asNum(v);
}

function Row({ l, v, tone }: { l: string; v: string; tone?: 'pos' | 'neg' }) {
  return (
    <div className="sg-kv">
      <span className="l">{l}</span>
      <span className={`v${tone === 'pos' ? ' pos-num' : tone === 'neg' ? ' neg-num' : ''}`}>{v}</span>
    </div>
  );
}

function Sect({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <p className="sg-sect">{title}</p>
      {children}
    </section>
  );
}

type MathsRow = { domain: string; score: number | null; weight: number | null; points: number | null; label: string };

function mathsRows(explain: Record<string, unknown> | null): MathsRow[] {
  if (!explain) return [];
  const raw = explain.maths;
  if (!Array.isArray(raw)) return [];
  return raw
    .map((m) => {
      const o = getObj(m);
      if (!o) return null;
      return {
        domain: asStr(o.domain) ?? '—',
        score: n(o.score),
        weight: n(o.weight),
        points: n(o.points),
        label: asStr(o.label) ?? '',
      };
    })
    .filter((r): r is MathsRow => r !== null);
}

function strList(v: unknown, max = 10): string[] {
  if (!Array.isArray(v)) return [];
  const out: string[] = [];
  for (const item of v) {
    const s = asStr(item);
    if (s) out.push(s);
    if (out.length >= max) break;
  }
  return out;
}

function fmtT(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—';
  const ms = typeof v === 'number' && Number.isFinite(v) ? (v < 1e12 ? v * 1000 : v) : new Date(String(v)).getTime();
  if (!Number.isFinite(ms)) return '—';
  const d = new Date(ms);
  return d.toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function fmtDur(sec: unknown): string {
  const s = n(sec);
  if (s === null) return '—';
  if (s < 60) return `${Math.round(s)}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${Math.round(s % 60)}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

export function SignalDetailDrawer({ signalId, onClose }: { signalId: string | null; onClose: () => void }) {
  const [deep, setDeep] = useState<Record<string, unknown> | null>(null);
  const [audit, setAudit] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  const load = useCallback(async () => {
    if (!signalId) return;
    setLoading(true);
    setErrors([]);
    const [d, a] = await Promise.all([
      api.getSignalDeepDive(signalId).catch((e) => ({ __err: e instanceof Error ? e.message : 'deep-dive unavailable' })),
      api.getSingleSignalAudit(signalId).catch((e) => ({ __err: e instanceof Error ? e.message : 'audit unavailable' })),
    ]);
    const errs: string[] = [];
    const dObj = getObj(d);
    if (dObj && !('__err' in dObj)) setDeep(dObj);
    else {
      setDeep(null);
      if (dObj) errs.push(`Setup detail: ${String(dObj.__err)}`);
    }
    const aObj = getObj(a);
    if (aObj && !('__err' in aObj)) setAudit(aObj);
    else {
      setAudit(null);
      if (aObj) errs.push(`Ledger record: ${String(aObj.__err)}`);
    }
    setErrors(errs);
    setLoading(false);
  }, [signalId]);

  useEffect(() => {
    if (signalId) void load();
    else {
      setDeep(null);
      setAudit(null);
      setErrors([]);
    }
  }, [signalId, load]);

  /* Live refresh for open positions (5s, visible tab only). */
  useEffect(() => {
    if (!signalId) return;
    const t = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      void load();
    }, 5000);
    return () => clearInterval(t);
  }, [signalId, load]);

  useEffect(() => {
    if (!signalId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [signalId, onClose]);

  if (!signalId) return null;

  const sig = deep ? getObj(deep.signal) : null;
  const explain = deep ? getObj(deep.explain) : null;
  const src: Record<string, unknown> = sig ?? audit ?? {};
  const symbol = pickStr(src, 'underlying', 'instrument', 'symbol') ?? '—';
  const strategy = pickStr(src, 'strategy') ?? '—';
  const dirRaw = src.direction ?? 'NEUTRAL';
  const dirNorm = normalizeDirection(dirRaw);
  const state = pickStr(src, 'fsm_state', 'status', 'state') ?? '—';
  const conf = pickNum(src, 'confidence', 'score');
  const verdict = explain ? getObj(explain.verdict) : null;

  /* Levels: prefer deep-dive levels block, else raw fields. */
  const lv = deep ? getObj(deep.levels) : null;
  const entryRange = Array.isArray(lv?.entry_range) ? (lv?.entry_range as unknown[]) : null;
  const trig = n(lv?.trigger) ?? pickNum(src, 'trigger', 'trigger_price', 'trigger_level');
  const sl = n(lv?.stop_loss) ?? pickNum(src, 'stop_loss', 'sl');
  const t1 = n(lv?.target_1) ?? pickNum(src, 'target_1', 't1');
  const t2 = n(lv?.target_2) ?? pickNum(src, 'target_2', 't2');
  const riskPts = n(lv?.risk_points) ?? pickNum(src, 'risk_points');
  const rr1 = n(lv?.risk_reward_t1) ?? pickNum(src, 'risk_reward_t1');
  const rr2 = n(lv?.risk_reward_t2) ?? pickNum(src, 'risk_reward_t2');
  const curPx = n(deep?.current_market_price) ?? pickNum(audit ?? {}, 'current_price') ?? pickNum(src, 'spot_price');
  const spotAtCreation = pickNum(src, 'spot_price', 'spot_price_at_creation');

  /* Execution: audit first, FSM paper_order second. */
  const fill = pickNum(audit ?? {}, 'actual_fill_price', 'fill_price') ?? pickNum(sig ?? {}, 'actual_fill_price', 'entry_price');
  const qty = pickNum(audit ?? {}, 'quantity', 'qty') ?? pickNum(sig ?? {}, 'quantity', 'intended_qty');
  const lots = pickNum(audit ?? {}, 'lots') ?? pickNum(sig ?? {}, 'lots');
  const orderId = pickStr(audit ?? {}, 'paper_order_id') ?? pickStr(getObj(sig?.paper_order) ?? {}, 'order_id');
  const margin = pickNum(audit ?? {}, 'margin_used');
  const slip = pickNum(audit ?? {}, 'slippage_points');
  const exitPx = pickNum(audit ?? {}, 'exit_price') ?? pickNum(sig ?? {}, 'exit_price');
  const exitReason = pickStr(audit ?? {}, 'exit_reason', 'outcome_label') ?? pickStr(sig ?? {}, 'terminal_outcome', 'outcome_status');
  const holdSec = pickNum(audit ?? {}, 'holding_time_seconds');
  const rpnl = pickNum(audit ?? {}, 'actual_pnl_inr');
  const upnl = pickNum(audit ?? {}, 'unrealized_pnl_inr');
  const tpnl = pickNum(audit ?? {}, 'total_pnl_inr');
  const maxLoss = fill !== null && qty !== null ? fill * qty : null;
  const isOpen = /^(ARMED|CONFIRMED|EXECUTED|TARGET_1_HIT)$/.test(state.toUpperCase());

  /* Contract. */
  const contract = getObj(sig?.option_contract) ?? getObj(audit?.option_contract);
  const optSym = pickStr(audit ?? {}, 'option_symbol') ?? pickStr(contract ?? {}, 'broker_symbol', 'symbol');
  const strike = n(contract?.strike) ?? pickNum(audit ?? {}, 'option_strike');
  const optType = pickStr(contract ?? {}, 'option_type') ?? pickStr(audit ?? {}, 'option_type');
  const expiry = pickStr(contract ?? {}, 'expiry') ?? pickStr(audit ?? {}, 'expiry');
  const lotSize = n(contract?.lot_size) ?? pickNum(audit ?? {}, 'lot_size');

  /* Mechanism. */
  const maths = mathsRows(explain);
  const penalties = explain ? strList(explain.penalties, 6) : [];
  const gatesPassed = explain ? strList(explain.gates_passed, 8) : [];
  const gatesRejected = explain ? strList(explain.gates_rejected_by_others, 8) : [];
  const whyLayman = explain ? strList(explain.why_layman, 7) : [];
  const changeMind = explain ? strList(explain.what_would_change_mind, 4) : [];
  const strategyRule = explain ? asStr(explain.strategy_rule) : null;
  const snap = explain ? getObj(explain.inputs_snapshot) : null;
  const ind = snap ? getObj(snap.indicators) : null;
  const fno = snap ? getObj(snap.fno) : null;
  const health = explain ? getObj(explain.data_health) : null;
  const rationale = Array.isArray(sig?.rationale) ? strList(sig?.rationale, 6) : [];
  const sizing = deep ? getObj(deep.position_sizing_preview) : null;

  /* Lifecycle timeline: FSM + audit histories merged by timestamp. */
  type TL = { ts: number; from: string; to: string; reason: string; price: number | null };
  const timeline: TL[] = [];
  const pushHist = (list: unknown, fromK: string, toK: string, tsK: string[], reasonK: string[], priceK: string[]) => {
    if (!Array.isArray(list)) return;
    for (const h of list) {
      const o = getObj(h);
      if (!o) continue;
      let ts: number | null = null;
      for (const k of tsK) {
        const v = o[k];
        if (typeof v === 'number' && Number.isFinite(v)) {
          ts = v < 1e12 ? v * 1000 : v;
          break;
        }
      }
      if (ts === null) continue;
      let price: number | null = null;
      for (const k of priceK) {
        const pv = n(o[k]);
        if (pv !== null) {
          price = pv;
          break;
        }
      }
      timeline.push({
        ts,
        from: asStr(o[fromK]) ?? '—',
        to: asStr(o[toK]) ?? '—',
        reason: reasonK.map((k) => asStr(o[k])).find((s) => s) ?? '',
        price,
      });
    }
  };
  pushHist(sig?.state_history, 'from_state', 'to_state', ['timestamp_utc', 'at'], ['reason'], ['market_price', 'price']);
  pushHist(audit?.state_history, 'from_state', 'to_state', ['timestamp_utc', 'at'], ['reason'], ['market_price', 'price']);
  timeline.sort((a, b) => a.ts - b.ts);

  const dist = trig !== null && curPx !== null && trig !== 0 ? ((curPx - trig) / Math.abs(trig)) * 100 : null;

  return (
    <div className="sg-ovl" onClick={onClose} role="presentation">
      <aside className="sg-drawer" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={`Signal dossier ${signalId}`}>
        <div className="sg-dhead">
          <div>
            <p className="sg-eyebrow">Signal dossier</p>
            <h3 className="sg-dtitle">
              {symbol} <span className="sg-strat">· {strategy.replace(/_/g, ' ').toLowerCase()}</span>
            </h3>
            <div className="sg-dtags">
              <span className={`sg-dir ${dirNorm === 'BULLISH' ? 'long' : dirNorm === 'BEARISH' ? 'short' : ''}`} style={dirNorm === 'NEUTRAL' ? { color: 'var(--sg-ink-3)' } : undefined}>
                {dirNorm === 'NEUTRAL' ? 'NEUTRAL' : dirNorm === 'BULLISH' ? 'LONG' : 'SHORT'}
              </span>
              <span className={`sg-tag ${stateTone(state) === 'bull' ? 'bull' : stateTone(state) === 'bear' ? 'bear' : stateTone(state) === 'info' ? 'info' : stateTone(state) === 'warn' ? 'warn' : 'neut'}`}>{state}</span>
              {conf !== null ? <span className="sg-num" style={{ fontWeight: 700 }}>{conf > 1 ? `${conf.toFixed(1)}%` : `${Math.round(conf * 100)}%`} CONF</span> : null}
            </div>
          </div>
          <div className="sg-dactions">
            <button type="button" className="sg-ibtn" title="Refresh dossier" onClick={() => void load()} disabled={loading}>
              <RefreshCw size={13} />
            </button>
            <button type="button" className="sg-ibtn" title="Close (Esc)" onClick={onClose}>
              <X size={14} />
            </button>
          </div>
        </div>

        <div className="sg-dbody">
          {loading && !deep && !audit ? (
            <div style={{ display: 'grid', gap: 8, padding: '4px 0' }}>
              {[0, 1, 2].map((i) => (
                <div key={i} className="skel" style={{ height: 12, width: `${80 - i * 12}%` }}>.</div>
              ))}
            </div>
          ) : null}
          {errors.length ? (
            <div className="sg-warnbox">
              {errors.map((e, i) => (
                <p key={i}>{e}</p>
              ))}
            </div>
          ) : null}

          <Sect title="Decision summary">
            <div className="sg-kvlist">
              <Row l="Verdict" v={verdict ? `${String(verdict.direction ?? '—')} @ ${n(verdict.confidence) !== null ? `${(n(verdict.confidence) as number).toFixed(1)}` : '—'}` : '—'} />
              <Row l="Fused vs armed" v={explain ? `${n(getObj(explain.verdict)?.confidence)?.toFixed?.(1) ?? '—'} / ${n(explain.threshold_armed) ?? '—'} (v${String(explain.weights_version ?? '?')})` : '—'} />
              <Row l="Live vs trigger" v={curPx !== null && trig !== null ? `${fmtINR(curPx)} vs ${fmtINR(trig)}${dist !== null ? ` (${dist >= 0 ? '+' : ''}${dist.toFixed(2)}%)` : ''}` : '—'} />
              <Row l="Risk : reward" v={rr1 !== null || rr2 !== null ? `${rr1 ?? '—'}R / ${rr2 ?? '—'}R` : '—'} />
              <Row
                l="Capital at risk"
                v={maxLoss !== null ? `−${fmtINR(maxLoss)} max (option buy)` : '—'}
                tone={maxLoss !== null ? 'neg' : undefined}
              />
              <Row
                l="Position P&L"
                v={!isOpen && rpnl !== null ? `${rpnl >= 0 ? '+' : ''}${fmtINR(rpnl)} realized` : isOpen && upnl !== null ? `${upnl >= 0 ? '+' : ''}${fmtINR(upnl)} live MTM` : '—'}
                tone={(!isOpen ? rpnl : upnl) !== null && ((isOpen ? upnl : rpnl) as number) !== null ? (((isOpen ? upnl : rpnl) as number) > 0 ? 'pos' : ((isOpen ? upnl : rpnl) as number) < 0 ? 'neg' : undefined) : undefined}
              />
              <Row l="State" v={isOpen ? (fill !== null ? 'OPEN — capital deployed, stop governs' : 'PENDING — no capital deployed yet') : 'CLOSED — booked, see execution'} />
            </div>
          </Sect>

          <Sect title="Why this signal — confluence mechanism">
            {maths.length ? (
              <table className="sg-mini">
                <thead>
                  <tr><th>Domain</th><th className="r">Score</th><th className="r">Wt</th><th className="r">Pts</th></tr>
                </thead>
                <tbody>
                  {maths.map((m) => (
                    <tr key={m.domain}>
                      <td><span className="sg-strat">{m.label || m.domain}</span></td>
                      <td className="r sg-num">{m.score === null ? '—' : m.score.toFixed(1)}</td>
                      <td className="r sg-num">{m.weight === null ? '—' : `${Math.round(m.weight * 100)}%`}</td>
                      <td className="r sg-num" style={{ fontWeight: 700 }}>{m.points === null ? '—' : m.points.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="sg-note">Setup detail expired from memory — execution and lifecycle below are authoritative.</p>
            )}
            {penalties.length ? (
              <div className="sg-flags">
                {penalties.map((p, i) => (
                  <p key={i} className="sg-flag warn">▲ {p}</p>
                ))}
              </div>
            ) : null}
            {whyLayman.length ? (
              <ul className="sg-list">
                {whyLayman.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            ) : null}
            {strategyRule ? <p className="sg-note">Rule: {strategyRule}</p> : null}
            {rationale.length ? (
              <ul className="sg-list">
                {rationale.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            ) : null}
            {gatesPassed.length ? <p className="sg-note">Gates passed: {gatesPassed.join(' · ')}</p> : null}
            {gatesRejected.length ? <p className="sg-note">Rejected elsewhere: {gatesRejected.join(' · ')}</p> : null}
            {changeMind.length ? (
              <>
                <p className="sg-sect" style={{ marginTop: 10 }}>Invalidation — what changes the thesis</p>
                <ul className="sg-list">
                  {changeMind.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </>
            ) : null}
            {snap || health ? (
              <div className="sg-kvlist" style={{ marginTop: 8 }}>
                {n(snap?.spot) !== null ? <Row l="Spot @ scan" v={fmtINR(n(snap?.spot))} /> : null}
                {n(snap?.vwap) !== null ? <Row l="VWAP @ scan" v={fmtINR(n(snap?.vwap))} /> : null}
                {asStr(snap?.regime) ? <Row l="Regime" v={String(asStr(snap?.regime)).toUpperCase()} /> : null}
                {ind && n(ind.rsi) !== null ? <Row l="RSI" v={String(n(ind.rsi))} /> : null}
                {ind && n(ind.adx) !== null ? <Row l="ADX" v={String(n(ind.adx))} /> : null}
                {fno && n(fno.pcr) !== null ? <Row l="PCR" v={String(n(fno.pcr))} /> : null}
                {health && (health.fno_degraded || health.vwap_degraded || health.degraded) ? (
                  <Row l="Data health" v="DEGRADED — size down" tone="neg" />
                ) : (
                  <Row l="Data health" v="clean" tone="pos" />
                )}
              </div>
            ) : null}
          </Sect>

          <Sect title="Levels & risk">
            <div className="sg-kvlist">
              <Row l="Entry zone" v={entryRange && entryRange.length >= 2 ? `${fmtINR(n(entryRange[0]))} – ${fmtINR(n(entryRange[1]))}` : trig !== null ? fmtINR(trig) : '—'} />
              <Row l="Trigger" v={trig !== null ? fmtINR(trig) : '—'} />
              <Row l="Stop loss" v={sl !== null ? fmtINR(sl) : '—'} />
              <Row l="Target 1 / 2" v={t1 !== null || t2 !== null ? `${t1 !== null ? fmtINR(t1) : '—'} / ${t2 !== null ? fmtINR(t2) : '—'}` : '—'} />
              <Row l="Risk" v={riskPts !== null ? `${riskPts.toFixed(2)} pts` : '—'} />
              <Row l="Spot @ creation" v={spotAtCreation !== null ? fmtINR(spotAtCreation) : '—'} />
              <Row l="Breakeven ratchet" v={sig ? (sig.breakeven_activated ? `ARMED @ ${fmtINR(n(sig.breakeven_activation_price))}` : 'not yet') : '—'} />
              <Row l="Lots / qty" v={lots !== null || qty !== null ? `${lots ?? '—'} / ${qty ?? '—'}` : '—'} />
              {margin !== null ? <Row l="Margin deployed" v={fmtINR(margin)} /> : null}
              {sizing ? (
                <Row
                  l="Size guide ₹1L / ₹5L"
                  v={`${n(getObj(sizing.account_1lakh)?.lots) ?? getObj(sizing.account_1lakh)?.lots ?? '—'} / ${n(getObj(sizing.account_5lakh)?.lots) ?? getObj(sizing.account_5lakh)?.lots ?? '—'} lots`}
                />
              ) : null}
            </div>
          </Sect>

          {contract || optSym ? (
            <Sect title="Option contract">
              <div className="sg-kvlist">
                {optSym ? <Row l="Symbol" v={optSym} /> : null}
                {pickStr(contract ?? {}, 'contract_source') ? (
                  <Row
                    l="Source"
                    v={pickStr(contract ?? {}, 'contract_source') === 'fyers_chain' ? 'FYERS chain (live)' : 'formula (offline fallback)'}
                    tone={pickStr(contract ?? {}, 'contract_source') === 'fyers_chain' ? 'pos' : 'neg'}
                  />
                ) : null}
                {strike !== null ? <Row l="Strike" v={fmtINR(strike)} /> : null}
                {optType ? <Row l="Type" v={optType} /> : null}
                {expiry ? <Row l="Expiry" v={expiry} /> : null}
                {lotSize !== null ? <Row l="Lot size" v={String(lotSize)} /> : null}
              </div>
            </Sect>
          ) : null}

          <Sect title={fill !== null ? 'Execution & P&L' : 'Execution'}>
            {fill === null ? (
              <p className="sg-note">Not executed — no order, no fill, no P&amp;L. Levels above are the plan, not a position.</p>
            ) : (
              <div className="sg-kvlist">
                <Row l="Fill" v={`${fmtINR(fill)} × ${qty ?? '—'}`} />
                {orderId ? <Row l="Order" v={orderId.slice(0, 18)} /> : null}
                <Row l="Filled at" v={fmtDateTimeMs(pickNum(audit ?? {}, 'executed_at_utc', 'executed_at') ?? pickNum(sig ?? {}, 'confirmed_at_utc'))} />
                {fill !== null && qty !== null ? <Row l="Entry value" v={`${fmtINR(fill)} × ${qty} = ${fmtINR(fill * qty)}`} /> : null}
                {slip !== null ? <Row l="Slippage" v={`${slip.toFixed(2)} pts`} /> : null}
                {exitPx !== null ? <Row l="Exit" v={`${fmtINR(exitPx)}${exitReason ? ` · ${exitReason}` : ''}`} /> : <Row l="Exit" v="open — runner live" />}
                {exitPx !== null ? <Row l="Exited at" v={fmtDateTimeMs(pickNum(audit ?? {}, 'exited_at_utc'))} /> : null}
                {exitPx !== null && qty !== null ? <Row l="Exit value" v={`${fmtINR(exitPx)} × ${qty} = ${fmtINR(exitPx * qty)}`} /> : null}
                {holdSec !== null || pickStr(audit ?? {}, 'holding_time_str') ? (
                  <Row l="Holding" v={pickStr(audit ?? {}, 'holding_time_str') ?? fmtDur(holdSec)} />
                ) : null}
                {rpnl !== null ? <Row l="Realized" v={`${rpnl >= 0 ? '+' : ''}${fmtINR(rpnl)}`} tone={rpnl > 0 ? 'pos' : rpnl < 0 ? 'neg' : undefined} /> : null}
                {isOpen && upnl !== null ? <Row l="Unrealized (live)" v={`${upnl >= 0 ? '+' : ''}${fmtINR(upnl)}`} tone={upnl > 0 ? 'pos' : upnl < 0 ? 'neg' : undefined} /> : null}
                {tpnl !== null ? <Row l="Net" v={`${tpnl >= 0 ? '+' : ''}${fmtINR(tpnl)}`} tone={tpnl > 0 ? 'pos' : tpnl < 0 ? 'neg' : undefined} /> : null}
              </div>
            )}
          </Sect>

          <Sect title="Lifecycle">
            {timeline.length ? (
              <ol className="sg-tl">
                {timeline.map((t, i) => (
                  <li key={i}>
                    <span className="sg-num">{fmtT(t.ts)}</span>
                    <span className="sg-tl-trans">{t.from} → {t.to}</span>
                    {t.price !== null ? <span className="sg-num">@ {fmtINR(t.price)}</span> : null}
                    {t.reason ? <span className="sg-tl-reason">{t.reason}</span> : null}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="sg-note">Created {fmtT(pickNum(src, 'created_at_utc', 'created_at_ms', 'created_at'))} · no transitions recorded yet.</p>
            )}
          </Sect>
        </div>
      </aside>
    </div>
  );
}

export default SignalDetailDrawer;

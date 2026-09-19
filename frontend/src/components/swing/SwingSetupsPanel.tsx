'use client';

import { FileText, Play } from 'lucide-react';
import type { SwingSetupDTO } from '@/lib/api/swing';
import { toNumber } from '@/lib/coerce';
import { fmtDateTimeMs, fmtExpiry, prettyKey, score0100ToPct } from '@/lib/signalsNormalize';
import { Meter } from '@/components/ui/desk';
import { safeNum } from '@/lib/utils';
import { swingEntryEligibility, swingSetupDirection, swingStateTone } from '@/lib/swingDesk';

function toMs(value: unknown): number | null {
  const n = toNumber(value);
  if (n === null) return null;
  return n < 1e12 ? Math.round(n * 1000) : Math.round(n);
}

function toneClass(tone: string): string {
  if (tone === 'bull') return 'bull';
  if (tone === 'bear') return 'bear';
  if (tone === 'warn') return 'warn';
  if (tone === 'info') return 'info';
  return 'neut';
}

export function SwingSetupsPanel({
  setups,
  busySetupId,
  onEnter,
  onThesis,
}: {
  setups: SwingSetupDTO[];
  busySetupId: string | null;
  onEnter: (setup: SwingSetupDTO) => void;
  onThesis: (setup: SwingSetupDTO) => void;
}) {
  if (setups.length === 0) {
    return (
      <section className="panel">
        <p className="sg-empty">
          No swing setups match the current filters. The scanner runs after the close (15:35 IST) or
          on demand with Scan now.
        </p>
      </section>
    );
  }

  return (
    <div className="tbl-scroll">
      <table className="sg-table">
        <thead>
          <tr>
            <th>Contract</th>
            <th>Dir</th>
            <th className="r">Score</th>
            <th className="r">Spot levels</th>
            <th className="r">Premium</th>
            <th className="r">Greeks</th>
            <th className="r">Risk / lot</th>
            <th>State</th>
            <th className="r">Actions</th>
          </tr>
        </thead>
        <tbody>
          {setups.map((setup) => {
            const direction = swingSetupDirection(setup);
            const eligibility = swingEntryEligibility(setup);
            const delta = toNumber(setup.greeks?.delta);
            const thetaDay = toNumber(setup.greeks?.theta_day);
            const vega = toNumber(setup.greeks?.vega);
            return (
              <tr key={setup.setup_id}>
                <td>
                  <div className="sg-sym">{setup.contract_symbol}</div>
                  <div className="sg-rownote">
                    {setup.underlying} · {setup.strike} {setup.option_type} · {fmtExpiry(setup.expiry_date)} · DTE {setup.dte}
                  </div>
                </td>
                <td>
                  <span className={`sg-dir ${direction === 'BEARISH' ? 'short' : 'long'}`}>
                    {direction === 'BEARISH' ? 'PUT' : direction === 'BULLISH' ? 'CALL' : '—'}
                  </span>
                  <div className="sg-rownote">{setup.horizon ?? 'POSITIONAL'}</div>
                </td>
                <td className="r">
                  <div className="num" style={{ fontWeight: 700 }}>
                    {safeNum(setup.score?.total, '—', 0)}
                  </div>
                  <Meter value={score0100ToPct(toNumber(setup.score?.total)) / 100} label="Setup score" />
                  <div className="sg-rownote">{prettyKey(setup.strategy)}</div>
                </td>
                <td className="r">
                  <div className="mono">{safeNum(setup.spot_price)}</div>
                  <div className="sg-rownote">
                    trig {safeNum(setup.spot_trigger)} · inv {safeNum(setup.spot_stop)}
                  </div>
                </td>
                <td className="r">
                  <div className="mono">E {safeNum(setup.entry_premium)} / S {safeNum(setup.stop_premium)}</div>
                  <div className="sg-rownote">
                    T1 {safeNum(setup.target_premium_1)} · T2 {safeNum(setup.target_premium_2)}
                  </div>
                </td>
                <td className="r">
                  <div className="mono">
                    Δ {safeNum(delta, '—', 2)} · Θ {safeNum(thetaDay, '—', 1)}
                  </div>
                  <div className="sg-rownote">ν {safeNum(vega, '—', 1)} · drag {safeNum(setup.theta_drag_ratio, '—', 1)}%</div>
                </td>
                <td className="r">
                  <div className="mono">₹{safeNum(setup.premium_risk_per_lot, '—', 0)}</div>
                  <div className="sg-rownote">
                    IV {safeNum(setup.iv, '—', 1)}% · {setup.iv_regime}
                  </div>
                </td>
                <td>
                  <span className={`sg-tag ${toneClass(swingStateTone(setup.signal_state))}`}>
                    {setup.signal_state}
                  </span>
                  <div className="sg-rownote">{fmtDateTimeMs(toMs(setup.created_at_utc))}</div>
                </td>
                <td>
                  <div className="sg-actions">
                    <button
                      type="button"
                      className="sg-ibtn"
                      title={eligibility.eligible ? 'Enter this setup into the swing book' : eligibility.reason ?? undefined}
                      disabled={!eligibility.eligible || busySetupId === setup.setup_id}
                      onClick={() => onEnter(setup)}
                    >
                      <Play size={12} />
                    </button>
                    <button
                      type="button"
                      className="sg-ibtn"
                      title="Build the structured AI thesis prompt for this setup"
                      onClick={() => onThesis(setup)}
                    >
                      <FileText size={12} />
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

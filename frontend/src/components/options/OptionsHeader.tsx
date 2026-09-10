'use client';

import { Card, Stat, fmtINR, fmtNum } from '@/components/ui/desk';
import { OptionsAnalytics } from '@/lib/types';

export function OptionsHeader({
  analytics,
  selectedSymbol,
  onSelectSymbol,
  selectedExpiry,
  expiries,
  onSelectExpiry,
  viewMode,
  onToggleViewMode,
}: {
  analytics: OptionsAnalytics | null;
  selectedSymbol: string;
  onSelectSymbol: (sym: string) => void;
  selectedExpiry: string;
  expiries: string[];
  onSelectExpiry: (exp: string) => void;
  viewMode: 'standard' | 'greeks';
  onToggleViewMode: (mode: 'standard' | 'greeks') => void;
}) {
  const symbols = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX'];

  return (
    <Card
      title="Options desk"
      meta={`${selectedSymbol}${selectedExpiry ? ` · ${selectedExpiry}` : ''}`}
    >
      <div className="toolbar">
        <div className="seg" role="group" aria-label="Underlying">
          {symbols.map((sym) => (
            <button
              key={sym}
              type="button"
              className="seg-btn"
              data-active={selectedSymbol === sym}
              aria-pressed={selectedSymbol === sym}
              onClick={() => onSelectSymbol(sym)}
            >
              {sym}
            </button>
          ))}
        </div>
        <span className="spacer" />
        <label className="muted" style={{ fontSize: 12 }} htmlFor="options-expiry">
          Expiry
        </label>
        <select
          id="options-expiry"
          value={selectedExpiry}
          onChange={(e) => onSelectExpiry(e.target.value)}
          className="btn"
          style={{ fontWeight: 600 }}
        >
          {expiries.map((exp) => (
            <option key={exp} value={exp}>
              {exp}
            </option>
          ))}
        </select>
        <div className="seg" role="group" aria-label="Chain view">
          <button
            type="button"
            className="seg-btn"
            data-active={viewMode === 'standard'}
            aria-pressed={viewMode === 'standard'}
            onClick={() => onToggleViewMode('standard')}
          >
            Standard
          </button>
          <button
            type="button"
            className="seg-btn"
            data-active={viewMode === 'greeks'}
            aria-pressed={viewMode === 'greeks'}
            onClick={() => onToggleViewMode('greeks')}
          >
            Greeks
          </button>
        </div>
      </div>

      <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', marginTop: 12 }}>
        <Stat
          label="Spot LTP"
          value={analytics?.spot_price ? fmtINR(analytics.spot_price) : '—'}
          sub={analytics?.futures_price ? `Fut ${fmtINR(analytics.futures_price)}` : 'Fut —'}
        />
        <Stat
          label="ATM strike"
          value={analytics?.atm_strike ? Number(analytics.atm_strike).toLocaleString('en-IN') : '—'}
          sub={analytics?.atm_iv ? `IV ${fmtNum(analytics.atm_iv, 1)}%` : 'IV —'}
        />
        <Stat
          label="PCR (OI)"
          value={analytics?.pcr_oi ?? '—'}
          sub={analytics?.pcr_volume != null ? `Vol PCR ${analytics.pcr_volume}` : 'Vol PCR —'}
          tone={
            analytics?.pcr_oi == null
              ? 'neut'
              : analytics.pcr_oi >= 1.2
                ? 'bull'
                : analytics.pcr_oi <= 0.8
                  ? 'bear'
                  : 'neut'
          }
        />
        <Stat
          label="Max pain"
          value={analytics?.max_pain_strike ? Number(analytics.max_pain_strike).toLocaleString('en-IN') : '—'}
          sub="Least option payout"
        />
        <Stat
          label="Days to expiry"
          value={analytics?.time_to_expiry_days !== undefined ? `${analytics.time_to_expiry_days}d` : '—'}
          sub="ACT/365"
        />
        <Stat
          label="Risk-free rate"
          value={analytics?.risk_free_rate ? `${(analytics.risk_free_rate * 100).toFixed(2)}%` : '6.75%'}
          sub={analytics?.rate_source ? String(analytics.rate_source) : 'IN benchmark'}
        />
      </div>
    </Card>
  );
}

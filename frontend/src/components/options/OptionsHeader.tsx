'use client';

import { Card, TelemetryItem, TelemetryStrip, fmtINR, fmtNum } from '@/components/ui/desk';
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
  callWall,
  putWall,
}: {
  analytics: OptionsAnalytics | null;
  selectedSymbol: string;
  onSelectSymbol: (sym: string) => void;
  selectedExpiry: string;
  expiries: string[];
  onSelectExpiry: (exp: string) => void;
  viewMode: 'standard' | 'greeks';
  onToggleViewMode: (mode: 'standard' | 'greeks') => void;
  callWall?: number | null;
  putWall?: number | null;
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

      <div style={{ marginTop: 10 }}>
        <TelemetryStrip>
          <TelemetryItem
            label="Spot LTP"
            value={analytics?.spot_price ? fmtINR(analytics.spot_price) : '—'}
            sub={analytics?.futures_price ? `Fut ${fmtINR(analytics.futures_price)}` : 'Fut —'}
          />
          <TelemetryItem
            label="ATM Strike"
            value={analytics?.atm_strike ? Number(analytics.atm_strike).toLocaleString('en-IN') : '—'}
            sub={
              typeof analytics?.atm_iv === 'number' && analytics.atm_iv > 0
                ? `IV ${fmtNum(analytics.atm_iv, 1)}%`
                : 'IV —'
            }
          />
          <TelemetryItem
            label="PCR (OI)"
            value={analytics?.pcr_oi ?? '—'}
            sub={analytics?.pcr_volume != null ? `Vol ${analytics.pcr_volume}` : 'Vol —'}
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
          <TelemetryItem
            label="Max Pain"
            value={analytics?.max_pain_strike ? Number(analytics.max_pain_strike).toLocaleString('en-IN') : '—'}
            sub="Least payout"
          />
          {callWall ? (
            <TelemetryItem
              label="Call Wall"
              value={`${callWall.toLocaleString('en-IN')} CE`}
              sub="Max Call OI"
              tone="bear"
            />
          ) : null}
          {putWall ? (
            <TelemetryItem
              label="Put Wall"
              value={`${putWall.toLocaleString('en-IN')} PE`}
              sub="Max Put OI"
              tone="bull"
            />
          ) : null}
          <TelemetryItem
            label="DTE"
            value={analytics?.time_to_expiry_days !== undefined ? `${analytics.time_to_expiry_days}d` : '—'}
            sub="ACT/365"
          />
        </TelemetryStrip>
      </div>
    </Card>
  );
}

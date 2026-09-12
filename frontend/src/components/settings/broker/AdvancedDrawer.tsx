'use client';
import React, { useState } from 'react';
import { Lock, ChevronDown, ChevronUp } from 'lucide-react';
import type { BrokerSettings } from '@/lib/settings';

interface Props {
  settings: BrokerSettings;
  onChange: (updates: Partial<BrokerSettings>) => void;
}

export function AdvancedDrawer({ settings, onChange }: Props) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showSecret, setShowSecret] = useState(false);

  return (
    <div className="card">
      <button
        type="button"
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="w-full card-hd text-xs font-semibold text-[var(--ds-ink-2)] hover:text-[var(--ds-ink)] transition-colors cursor-pointer"
      >
        <span className="flex items-center gap-2">
          <Lock className="w-3.5 h-3.5 muted" />
          <span>Advanced: Client Credentials Override (Optional)</span>
        </span>
        {showAdvanced ? <ChevronUp className="w-4 h-4 muted" /> : <ChevronDown className="w-4 h-4 muted" />}
      </button>
      {showAdvanced && (
        <div className="card-bd space-y-3 text-xs">
          <p className="text-[11px] muted leading-normal" style={{ margin: 0 }}>
            Leave empty to use credentials configured in Render Environment Variables. Enter values below only if you wish to override server defaults in this browser session.
          </p>
          {settings.provider === 'fyers' && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
              <div>
                <label className="text-xs font-semibold text-[var(--ds-ink)] block mb-1">Custom Fyers App ID (Override)</label>
                <input
                  type="text"
                  placeholder="e.g. HVMUH3H2LQ-100"
                  value={settings.fyers.appId}
                  onChange={(e) => onChange({ fyers: { ...settings.fyers, appId: e.target.value.trim() } })}
                  className="w-full bg-[var(--ds-surface)] border border-[var(--ds-border-strong)] rounded-[var(--radius-md)] px-2.5 py-1.5 text-xs text-[var(--ds-ink)] focus:outline-none focus:border-[var(--ds-accent)] mono"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-[var(--ds-ink)] block mb-1">Custom Secret Key (Override)</label>
                <div className="flex gap-2">
                  <input
                    type={showSecret ? 'text' : 'password'}
                    placeholder="Enter Secret Key"
                    value={settings.fyers.secret}
                    onChange={(e) => onChange({ fyers: { ...settings.fyers, secret: e.target.value.trim() } })}
                    className="w-full bg-[var(--ds-surface)] border border-[var(--ds-border-strong)] rounded-[var(--radius-md)] px-2.5 py-1.5 text-xs text-[var(--ds-ink)] focus:outline-none focus:border-[var(--ds-accent)] mono"
                  />
                  <button
                    type="button"
                    onClick={() => setShowSecret(!showSecret)}
                    className="btn btn-sm"
                  >
                    {showSecret ? 'Hide' : 'Show'}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

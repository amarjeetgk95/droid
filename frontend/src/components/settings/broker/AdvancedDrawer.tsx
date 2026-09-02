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
  const flattradeCreds = settings.flattrade || { userId: '', apiKey: '', apiSecret: '', redirectUri: '', token: '' };

  return (
    <div className="border border-border/60 rounded-xl overflow-hidden bg-card/50">
      <button
        type="button"
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="w-full flex items-center justify-between p-4 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
      >
        <span className="flex items-center gap-2">
          <Lock className="w-3.5 h-3.5" />
          Advanced: Custom UI Override (Optional)
        </span>
        {showAdvanced ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
      </button>
      {showAdvanced && (
        <div className="p-5 pt-0 border-t border-border/40 space-y-4 text-xs">
          <p className="text-[11px] text-muted-foreground mt-3">
            Leave empty to use credentials configured in Render Environment Variables. Enter values below only if you wish to override server defaults in this browser session.
          </p>
          {settings.provider === 'fyers' && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-semibold text-foreground block mb-1">Custom Fyers App ID (Override)</label>
                <input type="text" placeholder="e.g. HVMUH3H2LQ-100" value={settings.fyers.appId} onChange={(e) => onChange({ fyers: { ...settings.fyers, appId: e.target.value.trim() } })} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono" />
              </div>
              <div>
                <label className="text-xs font-semibold text-foreground block mb-1">Custom Secret Key (Override)</label>
                <div className="flex gap-2">
                  <input type={showSecret ? 'text' : 'password'} placeholder="Enter Secret Key" value={settings.fyers.secret} onChange={(e) => onChange({ fyers: { ...settings.fyers, secret: e.target.value.trim() } })} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono" />
                  <button type="button" onClick={() => setShowSecret(!showSecret)} className="text-[11px] px-2 py-1 border border-border rounded-lg hover:bg-secondary cursor-pointer bg-card">{showSecret ? 'Hide' : 'Show'}</button>
                </div>
              </div>
            </div>
          )}
          {settings.provider === 'flattrade' && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="text-xs font-semibold text-foreground block mb-1">Client Code (Override)</label>
                <input type="text" placeholder="e.g. FT012345" value={flattradeCreds.userId} onChange={(e) => onChange({ flattrade: { ...flattradeCreds, userId: e.target.value.trim() } })} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono" />
              </div>
              <div>
                <label className="text-xs font-semibold text-foreground block mb-1">API Key (Override)</label>
                <input type="text" placeholder="Enter API Key" value={flattradeCreds.apiKey} onChange={(e) => onChange({ flattrade: { ...flattradeCreds, apiKey: e.target.value.trim() } })} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono" />
              </div>
              <div>
                <label className="text-xs font-semibold text-foreground block mb-1">API Secret (Override)</label>
                <input type={showSecret ? 'text' : 'password'} placeholder="Enter API Secret" value={flattradeCreds.apiSecret} onChange={(e) => onChange({ flattrade: { ...flattradeCreds, apiSecret: e.target.value.trim() } })} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono" />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

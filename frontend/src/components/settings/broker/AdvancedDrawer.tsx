'use client';
import React from 'react';
import { Lock } from 'lucide-react';
import type { BrokerSettings } from '@/lib/settings';

interface Props {
  settings: BrokerSettings;
  onChange: (updates: Partial<BrokerSettings>) => void;
}

export function AdvancedDrawer({ settings }: Props) {
  if (settings.provider !== 'fyers') return null;
  return (
    <div className="card">
      <div className="w-full card-hd text-xs font-semibold text-[var(--ds-ink-2)]">
        <span className="flex items-center gap-2">
          <Lock className="w-3.5 h-3.5 muted" />
          <span>Broker credentials: managed by local backend</span>
        </span>
      </div>
      <div className="card-bd space-y-2 text-xs">
        <p className="text-[11px] muted leading-normal" style={{ margin: 0 }}>
          App ID / Secret are hardcoded in <code className="mono">backend/.env</code> (
          <code className="mono">FYERS_APP_ID</code> / <code className="mono">FYERS_SECRET_KEY</code>)
          on your localhost FastAPI (port 8000). Nothing secret is stored or edited in the
          browser — this fixes the old Saved-Settings vs env mismatch (
          <code className="mono">invalid app id hash</code>).
        </p>
        <p className="text-[11px] muted leading-normal" style={{ margin: 0 }}>
          To rotate: update <code className="mono">backend/.env</code>, restart the backend,
          update the Redirect URL in the Fyers dashboard to{' '}
          <code className="mono">http://127.0.0.1:8000/api/v1/tokens/fyers/callback</code>,
          then click Authorize with FYERS.
        </p>
      </div>
    </div>
  );
}

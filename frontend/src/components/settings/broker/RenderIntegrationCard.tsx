'use client';
import React, { useState } from 'react';
import { Server, ShieldCheck, Copy, Check, ExternalLink, Lock } from 'lucide-react';
import type { BrokerSettings } from '@/lib/settings';
import { REDIRECT_BASE, FYERS_LOGIN_URL, FLATTRADE_LOGIN_URL } from './constants';

interface Props {
  settings: BrokerSettings;
}

export function RenderIntegrationCard({ settings }: Props) {
  const [copiedRedirect, setCopiedRedirect] = useState(false);
  const handleCopyRedirect = (provider: 'fyers' | 'flattrade') => {
    const uri = `${REDIRECT_BASE}/${provider}/callback`;
    navigator.clipboard.writeText(uri);
    setCopiedRedirect(true);
    setTimeout(() => setCopiedRedirect(false), 2000);
  };

  if (settings.apiType !== 'indian') return null;

  const fyersServerLoginUrl = FYERS_LOGIN_URL;
  const flattradeServerLoginUrl = FLATTRADE_LOGIN_URL;

  return (
    <div className="bg-card border border-primary/20 rounded-xl p-5 space-y-4 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-primary/10 text-primary">
            <Server className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <span>Render Backend Integration</span>
              <span className="text-[10px] px-2 py-0.5 rounded-full font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1">
                <Lock className="w-2.5 h-2.5" />
                Keys Managed on Render
              </span>
            </h3>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Your App ID, API Secret, and OAuth exchanges are handled directly by your Render service (<code>droid-backend-emeq</code>).
            </p>
          </div>
        </div>
        <a
          href={settings.provider === 'fyers' ? 'https://myapi.fyers.in/dashboard' : 'https://wallconnect.flattrade.in/'}
          target="_blank"
          rel="noreferrer"
          className="text-xs text-primary hover:underline flex items-center gap-1 font-medium shrink-0"
        >
          <span>{settings.provider === 'fyers' ? 'Fyers Portal' : 'WallConnect Portal'}</span>
          <ExternalLink className="w-3 h-3" />
        </a>
      </div>

      <div className="p-3.5 bg-secondary/40 rounded-xl border border-border/50 space-y-2.5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
          <span className="text-muted-foreground font-medium">
            Render Callback URL (Configure in {settings.provider === 'fyers' ? 'Fyers' : 'Flattrade'} Portal):
          </span>
          <div className="flex items-center gap-2">
            <code className="text-[11px] font-mono bg-background/80 px-2 py-1 rounded border border-border/60 text-sky-300">
              {REDIRECT_BASE}/{settings.provider}/callback
            </code>
            <button
              type="button"
              onClick={() => handleCopyRedirect(settings.provider as 'fyers' | 'flattrade')}
              className="flex items-center gap-1 px-2.5 py-1 bg-secondary hover:bg-secondary/80 text-foreground rounded text-[11px] font-medium transition-all cursor-pointer border border-border"
            >
              {copiedRedirect ? (
                <>
                  <Check className="w-3 h-3 text-emerald-400" />
                  <span>Copied!</span>
                </>
              ) : (
                <>
                  <Copy className="w-3 h-3" />
                  <span>Copy</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      <div className="p-4 rounded-xl border border-primary/20 bg-primary/5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="space-y-0.5">
          <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <ShieldCheck className="w-4 h-4 text-primary" />
            Daily 1-Click Authentication (SEBI Compliant)
          </div>
          <p className="text-[11px] text-muted-foreground leading-relaxed">
            Render will automatically fetch server keys, process the 2FA login, and activate your 24-hour market feed.
          </p>
        </div>
        <a
          href={settings.provider === 'fyers' ? fyersServerLoginUrl : flattradeServerLoginUrl}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-2 px-4 py-2.5 bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold rounded-lg shadow-sm transition-all cursor-pointer whitespace-nowrap"
        >
          <span>{settings.provider === 'fyers' ? 'Login & Authorize with FYERS' : 'Login & Authorize with Flattrade'}</span>
          <ExternalLink className="w-3.5 h-3.5" />
        </a>
      </div>
    </div>
  );
}

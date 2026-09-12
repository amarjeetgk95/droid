'use client';

import React, { useState, useEffect } from 'react';
import { Server, Copy, Check, ExternalLink, Loader2 } from 'lucide-react';
import type { BrokerSettings } from '@/lib/settings';
import { REDIRECT_BASE, FYERS_LOGIN_URL } from './constants';
import { SettingSection, SettingRow } from '../ui/SettingPrimitives';
import { openBrokerAuth } from '@/lib/brokerAuth';
import { cn } from '@/lib/utils';

interface Props {
  settings: BrokerSettings;
}

export function RenderIntegrationCard({ settings }: Props) {
  const [copiedRedirect, setCopiedRedirect] = useState(false);
  const [isAuthorizing, setIsAuthorizing] = useState(false);
  const [authSuccess, setAuthSuccess] = useState(false);

  useEffect(() => {
    const handleAuth = () => {
      setIsAuthorizing(false);
      setAuthSuccess(true);
      setTimeout(() => setAuthSuccess(false), 4000);
    };
    window.addEventListener('broker:authenticated', handleAuth);
    return () => window.removeEventListener('broker:authenticated', handleAuth);
  }, []);

  const handleCopyRedirect = () => {
    const uri = `${REDIRECT_BASE}/fyers/callback`;
    navigator.clipboard.writeText(uri);
    setCopiedRedirect(true);
    setTimeout(() => setCopiedRedirect(false), 2000);
  };

  if (settings.apiType !== 'indian') return null;

  const portalUrl = 'https://myapi.fyers.in/dashboard';
  const portalName = 'Fyers Portal';

  const handleAuthorize = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsAuthorizing(true);
    setAuthSuccess(false);
    openBrokerAuth({
      provider: 'fyers',
      loginUrl: FYERS_LOGIN_URL,
      onSuccess: () => {
        setIsAuthorizing(false);
        setAuthSuccess(true);
        setTimeout(() => setAuthSuccess(false), 4000);
      },
      onClose: () => {
        setIsAuthorizing(false);
      },
      onError: () => {
        setIsAuthorizing(false);
      },
    });
  };

  return (
    <SettingSection
      title="Broker Gateway & Execution Session"
      description="Active Indian exchange broker (NSE/BSE) and 2FA OAuth session exchange."
      icon={Server}
      action={
        <a
          href={portalUrl}
          target="_blank"
          rel="noreferrer"
          className="btn btn-sm flex items-center gap-1.5"
        >
          <span>{portalName}</span>
          <ExternalLink className="w-3 h-3 muted" />
        </a>
      }
    >
      <SettingRow
        label="Execution Gateway"
        description="Low-latency Indian market broker for live tick feed and orders."
      >
        <div className="flex items-center gap-2">
          <span className="font-semibold text-xs text-[var(--ds-ink)]">FYERS API v3</span>
          <span className="badge b-info" style={{ fontSize: '10px', padding: '1px 6px' }}>
            NSE · BSE (INR)
          </span>
        </div>
      </SettingRow>

      <SettingRow
        label="OAuth Redirect URL"
        description="Set this callback URI in your Fyers developer dashboard application."
      >
        <div className="flex items-center gap-2">
          <code className="text-xs font-mono bg-[var(--ds-inset)] px-2 py-1 rounded border border-[var(--ds-border-strong)] text-[var(--ds-ink)]">
            {REDIRECT_BASE}/fyers/callback
          </code>
          <button
            type="button"
            onClick={handleCopyRedirect}
            className="btn btn-sm flex items-center gap-1"
          >
            {copiedRedirect ? (
              <>
                <Check className="w-3 h-3 text-[var(--ds-bull)]" />
                <span>Copied</span>
              </>
            ) : (
              <>
                <Copy className="w-3 h-3 muted" />
                <span>Copy</span>
              </>
            )}
          </button>
        </div>
      </SettingRow>

      <SettingRow
        label="Session Authorization"
        description="SEBI-mandated daily 2FA login. Activates 24-hour WebSocket feed and execution token."
      >
        <button
          type="button"
          onClick={handleAuthorize}
          disabled={isAuthorizing}
          className={cn(
            'btn btn-sm flex items-center gap-1.5 font-semibold',
            authSuccess
              ? 'btn-buy'
              : isAuthorizing
              ? 'btn-primary opacity-80 cursor-wait'
              : 'btn-primary',
          )}
        >
          {authSuccess ? (
            <>
              <Check className="w-3.5 h-3.5" />
              <span>FYERS Connected!</span>
            </>
          ) : isAuthorizing ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              <span>Authorizing FYERS…</span>
            </>
          ) : (
            <>
              <span>Authorize with FYERS</span>
              <ExternalLink className="w-3 h-3" />
            </>
          )}
        </button>
      </SettingRow>
    </SettingSection>
  );
}

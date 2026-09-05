'use client';

import React, { useState, useEffect } from 'react';
import { Server, Copy, Check, ExternalLink, Loader2 } from 'lucide-react';
import type { BrokerSettings } from '@/lib/settings';
import { REDIRECT_BASE, FYERS_LOGIN_URL, FLATTRADE_LOGIN_URL } from './constants';
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

  const handleCopyRedirect = (provider: 'fyers' | 'flattrade') => {
    const uri = `${REDIRECT_BASE}/${provider}/callback`;
    navigator.clipboard.writeText(uri);
    setCopiedRedirect(true);
    setTimeout(() => setCopiedRedirect(false), 2000);
  };

  if (settings.apiType !== 'indian') return null;

  const fyersServerLoginUrl = FYERS_LOGIN_URL;
  const flattradeServerLoginUrl = FLATTRADE_LOGIN_URL;
  const providerKey = settings.provider === 'fyers' ? 'fyers' : 'flattrade';
  const portalUrl =
    settings.provider === 'fyers'
      ? 'https://myapi.fyers.in/dashboard'
      : 'https://wallconnect.flattrade.in/';
  const portalName = settings.provider === 'fyers' ? 'Fyers Portal' : 'WallConnect Portal';

  const handleAuthorize = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsAuthorizing(true);
    setAuthSuccess(false);
    const loginUrl = settings.provider === 'fyers' ? fyersServerLoginUrl : flattradeServerLoginUrl;
    openBrokerAuth({
      provider: settings.provider,
      loginUrl,
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
      title="Backend Gateway & Authentication"
      description="OAuth callback endpoints and secure token exchange managed on your Render server."
      icon={Server}
      action={
        <a
          href={portalUrl}
          target="_blank"
          rel="noreferrer"
          className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1 transition-colors"
        >
          <span>{portalName}</span>
          <ExternalLink className="w-3 h-3" />
        </a>
      }
    >
      <SettingRow
        label="OAuth Redirect URL"
        description={`Set this exact callback URI in your ${settings.provider === 'fyers' ? 'Fyers' : 'Flattrade'} developer app console.`}
      >
        <div className="flex items-center gap-2">
          <code className="text-xs font-mono bg-secondary px-2 py-1 rounded border border-border/50 text-foreground">
            {REDIRECT_BASE}/{providerKey}/callback
          </code>
          <button
            type="button"
            onClick={() => handleCopyRedirect(providerKey)}
            className="flex items-center gap-1 px-2.5 py-1 bg-secondary hover:bg-secondary/80 text-foreground rounded text-xs font-medium transition-colors border border-border/60 cursor-pointer"
          >
            {copiedRedirect ? (
              <>
                <Check className="w-3 h-3 text-emerald-500" />
                <span>Copied</span>
              </>
            ) : (
              <>
                <Copy className="w-3 h-3 text-muted-foreground" />
                <span>Copy</span>
              </>
            )}
          </button>
        </div>
      </SettingRow>

      <SettingRow
        label="Session Authorization"
        description="SEBI-compliant daily 2FA login. Activates 24-hour WebSocket feed and execution token."
      >
        <button
          type="button"
          onClick={handleAuthorize}
          disabled={isAuthorizing}
          className={cn(
            'inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors shadow-2xs whitespace-nowrap cursor-pointer',
            authSuccess
              ? 'bg-emerald-600 text-white'
              : isAuthorizing
              ? 'bg-amber-500 text-slate-950 font-bold animate-pulse cursor-wait'
              : 'bg-primary hover:bg-primary/90 text-primary-foreground',
          )}
        >
          {authSuccess ? (
            <>
              <Check className="w-3.5 h-3.5" />
              <span>{settings.provider === 'fyers' ? 'FYERS' : 'Flattrade'} Connected!</span>
            </>
          ) : isAuthorizing ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              <span>Authorizing {settings.provider === 'fyers' ? 'FYERS' : 'Flattrade'}…</span>
            </>
          ) : (
            <>
              <span>Authorize with {settings.provider === 'fyers' ? 'FYERS' : 'Flattrade'}</span>
              <ExternalLink className="w-3 h-3" />
            </>
          )}
        </button>
      </SettingRow>
    </SettingSection>
  );
}

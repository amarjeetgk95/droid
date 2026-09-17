'use client';

import React from 'react';
import type { BadgeVariant } from '../shared/Badge';

/* ─────────────────────────── status dot ──────────────────────────────── */

type DotTone = 'up' | 'down' | 'warn' | 'neutral';

const dotTones: Record<DotTone, string> = {
  up: 'bg-up',
  down: 'bg-down',
  warn: 'bg-warn',
  neutral: 'bg-ink-4',
};

/** Small status dot; the pulse is disabled under `prefers-reduced-motion`. */
export const PulseDot: React.FC<{
  tone?: DotTone;
  pulse?: boolean;
  className?: string;
}> = ({ tone = 'neutral', pulse = true, className = '' }) => (
  <span
    aria-hidden="true"
    className={`inline-block h-1.5 w-1.5 rounded-full ${dotTones[tone]} ${
      pulse ? 'motion-safe:animate-pulse motion-reduce:animate-none' : ''
    } ${className}`}
  />
);

export function feedTone(health: string | null | undefined): DotTone {
  const s = (health ?? '').toUpperCase();
  if (s === 'HEALTHY' || s === 'LIVE') return 'up';
  if (s === 'RECENT' || s === 'STALE' || s === 'SYNCING') return 'warn';
  if (s === 'FEED_DEGRADED' || s === 'DISCONNECTED' || s === 'TRIPPED' || s === 'DOWN') {
    return 'down';
  }
  return 'neutral';
}

/* ─────────────────────────── notices ─────────────────────────────────── */

type NoticeTone = 'neutral' | 'warn' | 'down';

const noticeTones: Record<NoticeTone, string> = {
  neutral: 'text-ink-3',
  warn: 'text-warn-strong',
  down: 'text-down-strong',
};

/** Inline honest data state — loading / unavailable / error copy. */
export const PanelNotice: React.FC<{
  tone?: NoticeTone;
  role?: 'status' | 'alert';
  children: React.ReactNode;
  className?: string;
}> = ({ tone = 'neutral', role, children, className = '' }) => (
  <p role={role} className={`font-mono text-xs ${noticeTones[tone]} ${className}`}>
    {children}
  </p>
);

/* ─────────────────────── backend-state → badge aria ──────────────────── */

export function stateBadgeVariant(state: string | null | undefined): BadgeVariant {
  const s = (state ?? '').toUpperCase();
  if (s === 'CONFIRMED' || s === 'VALID') return 'success';
  if (s === 'POSSIBLE' || s === 'WATCH' || s === 'RECENT') return 'warning';
  if (s === 'REJECTED' || s === 'INVALIDATED' || s === 'EXPIRED' || s === 'FAILED') {
    return 'danger';
  }
  return 'neutral';
}

export function directionBadgeVariant(direction: string | null | undefined): BadgeVariant {
  const s = (direction ?? '').toUpperCase();
  if (s.includes('BULL')) return 'bull';
  if (s.includes('BEAR')) return 'bear';
  return 'neutral';
}

export function sentimentBadgeVariant(sentiment: string | null | undefined): BadgeVariant {
  const s = (sentiment ?? '').toUpperCase();
  if (s.includes('BULLISH')) return 'bull';
  if (s.includes('BEARISH')) return 'bear';
  if (s === 'MIXED') return 'warning';
  return 'neutral';
}

/* ─────────────────────────── formatting ──────────────────────────────── */

export function formatSigned(value: number | null, digits = 1, suffix = ''): string {
  if (value === null) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(digits)}${suffix}`;
}

export function formatStrike(value: number | null): string {
  if (value === null) return '—';
  return `₹${value.toLocaleString('en-IN')}`;
}

export function formatAge(at: number | null, now = Date.now()): string | null {
  if (at === null || !Number.isFinite(at)) return null;
  const seconds = Math.max(0, Math.round((now - at) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function formatIstTime(at: number | null): string | null {
  if (at === null || !Number.isFinite(at)) return null;
  try {
    return `${new Date(at).toLocaleTimeString('en-IN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
      timeZone: 'Asia/Kolkata',
    })} IST`;
  } catch {
    return null;
  }
}

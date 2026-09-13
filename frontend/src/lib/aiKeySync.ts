'use client';

// Cross-device AI key sync (Supabase -> this browser's localStorage).
//
// Problem it solves: AI screens resolve provider keys from localStorage, which
// is per-browser. A key saved in Settings on the PC lands in Supabase, but the
// phone's localStorage stays empty until the Settings page is opened there.
// This pull runs once at app boot (and throttled on focus) so AI works on any
// device straight after login — no manual Settings visit needed.
//
// Safety rules:
// - Only fills secrets that are non-empty in Supabase; a remote "" never
//   blanks a key already present locally.
// - A non-empty remote secret overwrites a differing local one (rotation on
//   one device propagates to the rest).
// - Never throws; backend unreachable => silent no-op.

import { api } from './api';
import { SECRET_FIELDS } from './settingsConstants';
import { getStoredSettings, saveStoredSettings } from './settingsStorage';

export const AI_SYNC_EVENT = 'droid:ai-keys-synced';

const SYNC_THROTTLE_MS = 60_000;

let lastSyncAt = 0;
let inFlight: Promise<boolean> | null = null;

export function syncAISecretsFromBackend(force = false): Promise<boolean> {
  if (typeof window === 'undefined') return Promise.resolve(false);
  const now = Date.now();
  if (!force && now - lastSyncAt < SYNC_THROTTLE_MS) return Promise.resolve(false);
  if (inFlight) return inFlight;
  inFlight = (async () => {
    try {
      const res = await api.getSettings();
      const remote = res?.app_settings as Record<string, unknown> | null | undefined;
      const remoteAi = remote && typeof remote === 'object'
        ? (remote.ai as Record<string, unknown> | undefined)
        : undefined;
      if (!remoteAi || typeof remoteAi !== 'object') return false;
      const local = getStoredSettings();
      const localAi = local.ai as unknown as Record<string, unknown>;
      let changed = false;
      for (const key of SECRET_FIELDS.ai) {
        const rv = remoteAi[key];
        if (typeof rv === 'string' && rv.trim() !== '' && localAi[key] !== rv) {
          localAi[key] = rv;
          changed = true;
        }
      }
      if (changed) {
        saveStoredSettings(local);
        window.dispatchEvent(new CustomEvent(AI_SYNC_EVENT));
      }
      return changed;
    } catch {
      // backend down / no row yet / offline — keep localStorage as-is
      return false;
    } finally {
      lastSyncAt = Date.now();
      inFlight = null;
    }
  })();
  return inFlight;
}

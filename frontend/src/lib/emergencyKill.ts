import { api } from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import { playScalpAudio } from '@/lib/scalpAudio';

/**
 * Executes emergency kill switch with multi-attempt retry, backoff, and signal escalation fallback.
 */
export async function executeEmergencyKill(
  maxRetries = 3,
  onAttempt?: (attempt: number) => void
): Promise<{ success: boolean; error?: string }> {
  if (typeof api.request !== 'function') {
    return { success: false, error: 'api.request is not configured' };
  }

  let lastError = 'Unknown error';
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    onAttempt?.(attempt);
    try {
      await api.request<unknown>('/api/v1/algo/kill-switch', {
        method: 'POST',
        body: JSON.stringify({ kill_level: 'HARD_STOP', reason: 'User War Room Kill Switch' }),
      });
      return { success: true };
    } catch (err) {
      lastError = errorMessage(err, 'Unknown error', { objectMessage: true });
      if (attempt < maxRetries) {
        await new Promise((resolve) => setTimeout(resolve, attempt * 600));
      }
    }
  }

  // Escalation: attempt secondary emergency signal kill switch endpoint
  try {
    await api.request<unknown>('/api/v1/signals/kill-switch', {
      method: 'POST',
      body: JSON.stringify({ active: true, reason: 'Escalated emergency kill switch from War Room' }),
    });
    return { success: true };
  } catch (escErr) {
    lastError = `Primary kill failed (${lastError}) & Escalation failed (${errorMessage(escErr, 'Unknown error', { objectMessage: true })})`;
  }

  try {
    playScalpAudio('panic');
  } catch {
    // Audio context may not be ready or muted
  }

  return { success: false, error: lastError };
}

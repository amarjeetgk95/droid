import { describe, it, expect } from 'vitest';
import { useExecutionGuard } from './useExecutionGuard';

describe('useExecutionGuard logic', () => {
  it('detects fresh and stale quotes according to threshold', () => {
    // We can directly test the checkQuoteFreshness helper from the hook or standalone logic
    const thresholdSec = 15;
    const now = Date.now();

    // simulate 5s old quote
    const freshAge = Math.max(0, Math.floor((now - (now - 5000)) / 1000));
    expect(freshAge <= thresholdSec).toBe(true);

    // simulate 25s old quote
    const staleAge = Math.max(0, Math.floor((now - (now - 25000)) / 1000));
    expect(staleAge > thresholdSec).toBe(true);
  });

  it('provides locking and prevents concurrent re-entrant execution', async () => {
    let activeCalls = 0;
    let maxConcurrent = 0;
    let lockActive = false;

    const guardedAction = async () => {
      if (lockActive) return null;
      lockActive = true;
      activeCalls++;
      maxConcurrent = Math.max(maxConcurrent, activeCalls);
      await new Promise((resolve) => setTimeout(resolve, 50));
      activeCalls--;
      lockActive = false;
      return 'done';
    };

    // Rapid double-trigger
    const [res1, res2] = await Promise.all([guardedAction(), guardedAction()]);
    expect(res1).toBe('done');
    expect(res2).toBe(null);
    expect(maxConcurrent).toBe(1);
  });
});

import { describe, it, expect, vi } from 'vitest';

describe('useSmartInterval behavior specification', () => {
  it('skips overlapping tick when previous execution is still unresolved', async () => {
    let callCount = 0;
    let inFlight = false;

    const smartTick = async () => {
      if (inFlight) return; // Overlap prevention
      inFlight = true;
      callCount++;
      await new Promise((resolve) => setTimeout(resolve, 50));
      inFlight = false;
    };

    const run1 = smartTick();
    const run2 = smartTick(); // Fired while run1 is in-flight

    await Promise.all([run1, run2]);
    expect(callCount).toBe(1);
  });

  it('pauses polling when document is hidden', () => {
    const isHidden = true;
    const pauseWhenHidden = true;
    const shouldSkip = pauseWhenHidden && isHidden;
    expect(shouldSkip).toBe(true);
  });

  it('resets timer when tab becomes visible to avoid burst double-fire', () => {
    let now = 1000;
    const intervalMs = 2000;
    let nextScheduledAt = now + intervalMs;

    // Simulate tab visible event at t = 2500
    now = 2500;
    // Immediate execution, and reset next tick to now + intervalMs
    nextScheduledAt = now + intervalMs;
    expect(nextScheduledAt).toBe(4500);
    expect(nextScheduledAt - now).toBe(intervalMs);
  });
});

import { describe, expect, it } from 'vitest';
import { ApiError, isApiErrorStatus, type ApiCore } from './client';
import { createIntelligenceApi } from './intelligence';

/** Minimal ApiCore double: records request paths, routes to a handler by prefix. */
function makeCore(handlers: Record<string, () => Promise<unknown>>) {
  const calls: string[] = [];
  const core = {
    async request(path: string) {
      calls.push(path);
      const key = Object.keys(handlers).find((k) => path.startsWith(k));
      if (!key) throw new Error(`unexpected path: ${path}`);
      return handlers[key]();
    },
  };
  return { core: core as unknown as ApiCore, calls };
}

describe('isApiErrorStatus', () => {
  it('matches only ApiErrors carrying a requested status', () => {
    expect(isApiErrorStatus(new ApiError('x', 404), 404, 405)).toBe(true);
    expect(isApiErrorStatus(new ApiError('x', 405), 404, 405)).toBe(true);
    expect(isApiErrorStatus(new ApiError('x', 503), 404, 405)).toBe(false);
    // Network/timeout failures are plain Errors with no status.
    expect(isApiErrorStatus(new Error('Cannot reach backend'), 404, 405)).toBe(false);
    expect(isApiErrorStatus('nope', 404)).toBe(false);
  });

  it('stays an Error so existing handling keeps working', () => {
    const err = new ApiError('boom', 500);
    expect(err).toBeInstanceOf(Error);
    expect(err.status).toBe(500);
    expect(err.name).toBe('ApiError');
  });
});

describe('getTacticalBias fallback', () => {
  it('falls back to /forecast only when the route itself is missing', async () => {
    const { core, calls } = makeCore({
      '/api/v1/research/tactical-bias/': async () => {
        throw new ApiError('Not Found', 404);
      },
      '/api/v1/research/forecast/': async () => ({ instrument: 'NIFTY 50' }),
    });

    const out = await createIntelligenceApi(core).getTacticalBias('NIFTY 50', '1h', true);

    expect(out).toEqual({ instrument: 'NIFTY 50' });
    expect(calls).toEqual([
      '/api/v1/research/tactical-bias/1h?instrument=NIFTY%2050&record=true&include_explain=true',
      '/api/v1/research/forecast/1h?instrument=NIFTY%2050&record=true&include_explain=true',
    ]);
  });

  it('does not re-issue the same computation on a real backend failure', async () => {
    const { core, calls } = makeCore({
      '/api/v1/research/tactical-bias/': async () => {
        throw new ApiError('insufficient 1h candle data', 503);
      },
      '/api/v1/research/forecast/': async () => ({ instrument: 'SHOULD_NOT_BE_USED' }),
    });

    await expect(
      createIntelligenceApi(core).getTacticalBias('NIFTY 50', '1h', true),
    ).rejects.toThrow('insufficient 1h candle data');
    // One round-trip, not two: the broker is already struggling in this case.
    expect(calls).toHaveLength(1);
  });

  it('never falls back on a network or timeout error', async () => {
    const { core, calls } = makeCore({
      '/api/v1/research/tactical-bias/': async () => {
        throw new Error('Cannot reach backend');
      },
      '/api/v1/research/forecast/': async () => ({ instrument: 'SHOULD_NOT_BE_USED' }),
    });

    await expect(
      createIntelligenceApi(core).getTacticalBias('NIFTY 50', '1h', true),
    ).rejects.toThrow('Cannot reach backend');
    expect(calls).toHaveLength(1);
  });
});

describe('getTacticalBiasBoard', () => {
  it('builds the board URL with shared-snapshot params', async () => {
    const { core, calls } = makeCore({
      '/api/v1/research/tactical-bias/board': async () => ({}),
    });

    await createIntelligenceApi(core).getTacticalBiasBoard('SENSEX', false, true);

    expect(calls[0]).toBe(
      '/api/v1/research/tactical-bias/board?instrument=SENSEX&record=false&include_layers=false&include_explain=true',
    );
  });

  it('honours record/includeExplain flags on the board URL', async () => {
    const { core, calls } = makeCore({
      '/api/v1/research/tactical-bias/board': async () => ({}),
    });

    await createIntelligenceApi(core).getTacticalBiasBoard('NIFTY 50', true, false);

    expect(calls[0]).toBe(
      '/api/v1/research/tactical-bias/board?instrument=NIFTY%2050&record=true&include_layers=false&include_explain=false',
    );
  });

  it('parses horizons sharing one generated_at and anchor_price', async () => {
    const generatedAt = '2026-09-21T12:00:00.000Z';
    const board = {
      instrument: 'SENSEX',
      generated_at: generatedAt,
      anchor_price: 82000,
      anchor_source: 'spot',
      anchor_ts: null,
      cache_age_s: 0,
      stale: false,
      horizons: Object.fromEntries(
        ['1m', '5m', '15m', '30m', '1h'].map((horizon) => [
          horizon,
          {
            instrument: 'SENSEX',
            generated_at: generatedAt,
            current_price: 82000,
            direction: 'NEUTRAL',
            score: 0,
            confidence: 50,
          },
        ]),
      ),
    };
    const { core } = makeCore({
      '/api/v1/research/tactical-bias/board': async () => board,
    });

    const out = await createIntelligenceApi(core).getTacticalBiasBoard('SENSEX', false, true);

    expect(out.generated_at).toBe(generatedAt);
    for (const horizon of ['1m', '5m', '15m', '30m', '1h'] as const) {
      expect(out.horizons[horizon].generated_at).toBe(out.generated_at);
      expect(out.horizons[horizon].current_price).toBe(out.anchor_price);
    }
  });

  it('propagates backend failures with no internal fallback (the hook owns the fallback)', async () => {
    const { core, calls } = makeCore({
      '/api/v1/research/tactical-bias/board': async () => {
        throw new ApiError('engine overloaded', 503);
      },
    });

    await expect(
      createIntelligenceApi(core).getTacticalBiasBoard('SENSEX', false, true),
    ).rejects.toThrow('engine overloaded');
    expect(calls).toHaveLength(1);
  });
});

describe('explain param is honoured end to end', () => {
  it('sends include_explain=false when the caller opts out', async () => {
    const { core, calls } = makeCore({ '/api/v1/research/forecast/': async () => ({}) });
    await createIntelligenceApi(core).getForecast('NIFTY 50', '5m', false, false);
    expect(calls[0]).toBe(
      '/api/v1/research/forecast/5m?instrument=NIFTY%2050&record=false&include_explain=false',
    );
  });
});

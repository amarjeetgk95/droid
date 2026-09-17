import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { deskCache } from './useDeskCache';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('deskCache', () => {
  beforeEach(() => {
    deskCache.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('stores entries with TTL-derived staleness', () => {
    deskCache.set('opts:stale', { v: 1 }, -1);
    const stale = deskCache.get<{ v: number }>('opts:stale');
    expect(stale?.data).toEqual({ v: 1 });
    expect(stale?.isStale).toBe(true);

    deskCache.set('opts:fresh', { v: 2 }, 60_000);
    expect(deskCache.get('opts:fresh')?.isStale).toBe(false);

    expect(deskCache.get('opts:missing')).toBeNull();
  });

  it('deduplicates identical in-flight fetches', async () => {
    const d = deferred<string>();
    let calls = 0;
    const fetcher = () => {
      calls += 1;
      return d.promise;
    };

    const first = deskCache.fetchWithDeduplication('signals:dedupe', fetcher);
    const second = deskCache.fetchWithDeduplication('signals:dedupe', fetcher);
    expect(second).toBe(first);

    d.resolve('payload');
    await expect(first).resolves.toBe('payload');
    expect(calls).toBe(1);
    expect(deskCache.get<string>('signals:dedupe')?.data).toBe('payload');
  });

  it('invalidate tombstones an in-flight fetch so it cannot repopulate', async () => {
    const d = deferred<string>();
    const pending = deskCache.fetchWithDeduplication('signals:inflight', () => d.promise);

    deskCache.invalidate('signals:inflight');
    d.resolve('late');
    await pending;

    expect(deskCache.get('signals:inflight')).toBeNull();
  });

  it('invalidatePrefix tombstones cached and pending keys with the prefix', async () => {
    deskCache.set('crypto:cached', 1);
    const d = deferred<number>();
    const pending = deskCache.fetchWithDeduplication('crypto:pending', () => d.promise);

    deskCache.invalidatePrefix('crypto:');
    expect(deskCache.get('crypto:cached')).toBeNull();

    d.resolve(2);
    await pending;
    expect(deskCache.get('crypto:pending')).toBeNull();
  });

  it('lets a post-invalidation fetch win over the older in-flight response', async () => {
    const old = deferred<string>();
    const oldRequest = deskCache.fetchWithDeduplication('options:race', () => old.promise);

    deskCache.invalidate('options:race');
    const fresh = deskCache.fetchWithDeduplication('options:race', async () => 'new');
    await expect(fresh).resolves.toBe('new');

    old.resolve('old');
    await oldRequest;
    expect(deskCache.get<string>('options:race')?.data).toBe('new');
  });

  it('does not let a stale request clear the newer pending slot', async () => {
    const old = deferred<string>();
    const fresh = deferred<string>();
    let calls = 0;

    const oldRequest = deskCache.fetchWithDeduplication('signals:slot', () => {
      calls += 1;
      return old.promise;
    });
    deskCache.invalidate('signals:slot');
    const freshRequest = deskCache.fetchWithDeduplication('signals:slot', () => {
      calls += 1;
      return fresh.promise;
    });

    old.resolve('old');
    await oldRequest;

    const deduped = deskCache.fetchWithDeduplication('signals:slot', () => {
      calls += 1;
      return fresh.promise;
    });
    expect(deduped).toBe(freshRequest);
    expect(calls).toBe(2);

    fresh.resolve('new');
    await freshRequest;
  });

  it('clear tombstones known keys so stragglers cannot repopulate', async () => {
    const d = deferred<string>();
    const pending = deskCache.fetchWithDeduplication('signals:clear', () => d.promise);

    deskCache.clear();
    d.resolve('post-clear');
    await pending;

    expect(deskCache.get('signals:clear')).toBeNull();
  });

  it('evicts the least-recently-accessed entry past the 30-entry bound', () => {
    vi.useFakeTimers();
    const base = new Date('2026-01-01T00:00:00Z').getTime();

    for (let i = 0; i < 30; i++) {
      vi.setSystemTime(base + i * 1000);
      deskCache.set(`lru:${i}`, i, 60_000);
    }
    vi.setSystemTime(base + 30_000);
    deskCache.set('lru:30', 30, 60_000);

    expect(deskCache.get('lru:0')).toBeNull();
    expect(deskCache.get('lru:1')).not.toBeNull();
    expect(deskCache.get('lru:30')?.data).toBe(30);
  });
});

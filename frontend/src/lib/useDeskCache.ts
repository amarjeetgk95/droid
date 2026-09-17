/**
 * useDeskCache
 *
 * Bounded In-Memory Stale-While-Revalidate (SWR) Desk Cache.
 *
 * Provides instant 0ms desk re-entry across route unmount/remount
 * during a session, with in-flight Promise deduplication, monotonic requestVersion
 * race protection, and LRU memory bounding.
 */

export interface DeskCacheEntry<T> {
  key: string;
  data: T;
  createdAt: number;
  expiresAt: number;
  lastAccessedAt: number;
  requestVersion: number;
}

/**
 * NOTE: no call sites import this module yet (verified by repo-wide search).
 * It is kept correct and self-contained so wiring it into a desk page is safe;
 * do not delete without checking with the perf workstream.
 */

const DEFAULT_TTLS: Record<string, number> = {
  options: 30_000, // 30s
  signals: 20_000, // 20s
  crypto: 10_000,  // 10s
  default: 30_000, // 30s
};

const MAX_CACHE_ENTRIES = 30;

/** Wrapper so an in-flight request can identify its own slot when clearing. */
interface PendingRequest<T> {
  promise: Promise<T>;
}

class DeskCacheStore {
  private cache = new Map<string, DeskCacheEntry<any>>();
  private pendingRequests = new Map<string, PendingRequest<unknown>>();
  private requestVersions = new Map<string, number>();

  private getTTL(key: string): number {
    const prefix = key.split(':')[0];
    return DEFAULT_TTLS[prefix] || DEFAULT_TTLS.default;
  }

  /**
   * Monotonic per-key version. Bumping on invalidation tombstones the key:
   * an in-flight fetch that resolves later sees `thisVersion < latestVersion`
   * and refuses to repopulate the cache with invalidated data.
   */
  private bumpVersion(key: string): number {
    const version = (this.requestVersions.get(key) || 0) + 1;
    this.requestVersions.set(key, version);
    return version;
  }

  /**
   * Read entry from cache. Returns null if missing.
   * If present, flags whether the cached data is currently stale.
   */
  get<T>(key: string): { data: T; isStale: boolean; createdAt: number } | null {
    const entry = this.cache.get(key) as DeskCacheEntry<T> | undefined;
    if (!entry) return null;

    entry.lastAccessedAt = Date.now();
    const isStale = Date.now() > entry.expiresAt;
    return { data: entry.data, isStale, createdAt: entry.createdAt };
  }

  /**
   * Store data in cache. Automatically enforces LRU bounds.
   */
  set<T>(key: string, data: T, customTtlMs?: number): void {
    const ttl = customTtlMs ?? this.getTTL(key);
    const now = Date.now();
    const version = this.bumpVersion(key);

    // LRU eviction if over capacity
    if (this.cache.size >= MAX_CACHE_ENTRIES && !this.cache.has(key)) {
      this.evictLRU();
    }

    this.cache.set(key, {
      key,
      data,
      createdAt: now,
      expiresAt: now + ttl,
      lastAccessedAt: now,
      requestVersion: version,
    });
  }

  /**
   * Execute fetch with in-flight Promise deduplication and requestVersion race protection.
   * Deliberately not `async`: an async wrapper would return a new promise on every
   * call and defeat the identity-based deduplication.
   */
  fetchWithDeduplication<T>(
    key: string,
    fetcher: () => Promise<T>,
    customTtlMs?: number
  ): Promise<T> {
    // 1. In-flight Promise deduplication: return existing pending request if present
    const existing = this.pendingRequests.get(key);
    if (existing) {
      return existing.promise as Promise<T>;
    }

    // 2. Track request version for race protection
    const thisVersion = this.bumpVersion(key);
    const entry = {} as PendingRequest<T>;

    entry.promise = (async () => {
      try {
        const result = await fetcher();

        // Check if an obsolete request resolved after a newer one / after invalidation
        const latestVersion = this.requestVersions.get(key) || 0;
        if (thisVersion >= latestVersion) {
          this.set(key, result, customTtlMs);
        }
        return result;
      } finally {
        // Only clear the slot if it still belongs to this request — invalidate()
        // may have replaced it with a newer pending request.
        if (this.pendingRequests.get(key) === entry) {
          this.pendingRequests.delete(key);
        }
      }
    })();

    this.pendingRequests.set(key, entry);
    return entry.promise;
  }

  invalidate(key: string): void {
    this.cache.delete(key);
    this.pendingRequests.delete(key);
    // Tombstone: any in-flight fetch for this key must not write back.
    this.bumpVersion(key);
  }

  invalidatePrefix(prefix: string): void {
    // Include pending-only and version-only keys so in-flight fetches that were
    // never cached are tombstoned too.
    const keys = new Set<string>([
      ...this.cache.keys(),
      ...this.pendingRequests.keys(),
      ...this.requestVersions.keys(),
    ]);
    for (const key of keys) {
      if (key.startsWith(prefix)) {
        this.invalidate(key);
      }
    }
  }

  clear(): void {
    const knownKeys = new Set<string>([
      ...this.cache.keys(),
      ...this.pendingRequests.keys(),
      ...this.requestVersions.keys(),
    ]);
    this.cache.clear();
    this.pendingRequests.clear();
    // Tombstone everything so stragglers cannot repopulate a cleared cache.
    for (const key of knownKeys) {
      this.bumpVersion(key);
    }
  }

  private evictLRU(): void {
    let oldestKey: string | null = null;
    let oldestAccess = Infinity;

    for (const [k, v] of this.cache.entries()) {
      if (v.lastAccessedAt < oldestAccess) {
        oldestAccess = v.lastAccessedAt;
        oldestKey = k;
      }
    }

    if (oldestKey) {
      this.cache.delete(oldestKey);
    }
  }
}

// Module-level singleton
export const deskCache = new DeskCacheStore();

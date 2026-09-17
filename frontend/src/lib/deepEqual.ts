/**
 * Lightweight deep equal without JSON.stringify allocation — for dirty checks.
 *
 * Handles the types that appear in app settings/desk state correctly:
 * - `NaN` is equal to `NaN` (dirty checks must not loop on a NaN field).
 * - `Date` instances compare by timestamp, not by zero enumerable keys.
 * - `Map` / `Set` compare by entries, not by zero enumerable keys.
 * - Arrays and plain objects recurse (key order is irrelevant).
 */

function objectTag(v: object): string {
  return Object.prototype.toString.call(v);
}

export function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;

  // NaN === NaN is false, but structurally they are the same dirty-check value.
  if (typeof a === 'number' && typeof b === 'number') {
    return Number.isNaN(a) && Number.isNaN(b);
  }

  if (a === null || b === null) return a === b;
  if (typeof a !== 'object' || typeof b !== 'object') return false;

  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) {
      if (!deepEqual(a[i], b[i])) return false;
    }
    return true;
  }

  const tagA = objectTag(a);
  const tagB = objectTag(b);

  if (tagA === '[object Date]' || tagB === '[object Date]') {
    if (tagA !== '[object Date]' || tagB !== '[object Date]') return false;
    const timeA = (a as Date).getTime();
    const timeB = (b as Date).getTime();
    return timeA === timeB || (Number.isNaN(timeA) && Number.isNaN(timeB));
  }

  if (tagA === '[object Map]' || tagB === '[object Map]') {
    if (tagA !== '[object Map]' || tagB !== '[object Map]') return false;
    const mapA = a as Map<unknown, unknown>;
    const mapB = b as Map<unknown, unknown>;
    if (mapA.size !== mapB.size) return false;
    for (const [key, value] of mapA) {
      if (!mapB.has(key)) return false;
      if (!deepEqual(value, mapB.get(key))) return false;
    }
    return true;
  }

  if (tagA === '[object Set]' || tagB === '[object Set]') {
    if (tagA !== '[object Set]' || tagB !== '[object Set]') return false;
    const setA = a as Set<unknown>;
    const setB = b as Set<unknown>;
    if (setA.size !== setB.size) return false;
    for (const value of setA) {
      if (!setB.has(value)) return false;
    }
    return true;
  }

  const ao = a as Record<string, unknown>;
  const bo = b as Record<string, unknown>;
  const aKeys = Object.keys(ao);
  const bKeys = Object.keys(bo);
  if (aKeys.length !== bKeys.length) return false;
  for (const k of aKeys) {
    if (!Object.prototype.hasOwnProperty.call(bo, k)) return false;
    if (!deepEqual(ao[k], bo[k])) return false;
  }
  return true;
}

/**
 * happy-dom exposes `window.happyDOM.setURL()` at runtime, but its type is not
 * part of the standard `Window` interface TypeScript sees. This helper keeps
 * the test files type-safe without per-file global casts.
 */
export function setTestUrl(url: string): void {
  const w = window as unknown as { happyDOM?: { setURL: (value: string) => void } };
  if (!w.happyDOM) {
    throw new Error('happy-dom setURL is unavailable in this test environment');
  }
  w.happyDOM.setURL(url);
}

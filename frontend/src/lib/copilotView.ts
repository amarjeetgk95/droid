/* Bird-eye copilot view pure parser: verdict/bias/bullets/levels/rest.
   No React, no I/O — safe to unit-test. Self-contained (does not import
   from copilot.ts to avoid client coupling). */

export type BirdBias = 'bull' | 'bear' | 'neut' | 'warn' | 'info';

export interface BirdView {
  verdict: string;
  bias: BirdBias;
  bullets: string[];
  levels: string[];
  rest: string;
}

/** Clamp a string by words. Returns '' for non-strings; appends … when truncated. */
export function clampWords(s: string, n: number): string {
  if (typeof s !== 'string') return '';
  if (!Number.isFinite(n) || n <= 0) return '';
  const words = s.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return '';
  if (words.length <= n) return words.join(' ');
  return words.slice(0, n).join(' ') + '…';
}

/** First sentence of a string (up to first . ! ?). Never throws. */
export function firstSentence(s: string): string {
  if (typeof s !== 'string') return '';
  const flat = s.replace(/\s+/g, ' ').trim();
  if (!flat) return '';
  const m = flat.match(/[^.?!]*[.?!](?=\s|$)/);
  if (m && m[0] && m[0].trim()) return m[0].trim();
  return flat;
}

function clampChars(s: string, n: number): string {
  const t = s.trim();
  if (t.length <= n) return t;
  return t.slice(0, n).trimEnd() + '…';
}

function cleanVerdictLine(line: string): string {
  let v = line.trim();
  for (let i = 0; i < 4; i++) {
    const prev = v;
    v = v.replace(/^#{1,6}\s*/, '').trim();
    v = v.replace(/^(\*\*|__)\s*/, '').trim();
    v = v.replace(/\s*(\*\*|__)$/, '').trim();
    v = v.replace(/^verdict\s*:\s*/i, '').trim();
    if (v === prev) break;
  }
  return v.trim();
}

const BULLET_RE = /^\s*(?:[-*•]\s+|\d+[.)]\s+)/;

function stripBulletMarker(line: string): string {
  return line.trim().replace(/^(?:[-*•]\s+|\d+[.)]\s+)/, '').trim();
}

const RUPEE_RE = /₹\s?[\d,]+(?:\.\d+)?/;
const LEVEL_KW_RE = /(levels|support|resistance|invalidation|\bsup\b|\bres\b)/i;

function safeDefaults(): BirdView {
  return { verdict: 'Market view', bias: 'neut', bullets: [], levels: [], rest: '' };
}

/**
 * Parse raw copilot markdown-ish text into a bird-eye view.
 * Never throws on null/undefined/non-string — returns safe defaults.
 */
export function toBirdView(raw: unknown): BirdView {
  try {
    if (typeof raw !== 'string') return safeDefaults();
    const lines = raw.split(/\r?\n/);

    let verdictIdx = -1;
    let verdictRaw = '';
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].trim() !== '') {
        verdictIdx = i;
        verdictRaw = lines[i];
        break;
      }
    }

    let verdict = 'Market view';
    if (verdictIdx >= 0) {
      const cleaned = cleanVerdictLine(verdictRaw);
      const clamped = clampWords(cleaned, 28);
      verdict = clamped ? clamped : 'Market view';
    }

    const hay = `${verdict} ${raw}`.toUpperCase();
    let bias: BirdBias = 'neut';
    if (/(BULL|CONFIRM|LONG|BUY)/.test(hay)) bias = 'bull';
    else if (/(BEAR|REJECT|SHORT|SELL)/.test(hay)) bias = 'bear';
    else if (/(WATCH|WAIT|UNCERTAIN|VOLATILE)/.test(hay)) bias = 'warn';
    else if (/(ARMED|READY|TRIGGERED|LIVE)/.test(hay)) bias = 'info';

    const bullets: string[] = [];
    const bulletIdx = new Set<number>();
    if (verdictIdx >= 0) {
      for (let i = verdictIdx + 1; i < lines.length && bullets.length < 3; i++) {
        const t = lines[i].trim();
        if (!t) continue;
        if (BULLET_RE.test(t)) {
          const content = stripBulletMarker(t);
          if (!content) continue;
          bullets.push(clampWords(content, 22));
          bulletIdx.add(i);
        }
      }
    }

    const levels: string[] = [];
    for (let i = 0; i < lines.length && levels.length < 4; i++) {
      const t = lines[i].trim();
      if (!t) continue;
      if (RUPEE_RE.test(t) || LEVEL_KW_RE.test(t)) {
        levels.push(clampChars(t, 80));
      }
    }

    let rest = '';
    if (verdictIdx >= 0) {
      const parts: string[] = [];
      for (let i = verdictIdx + 1; i < lines.length; i++) {
        if (bulletIdx.has(i)) continue;
        parts.push(lines[i]);
      }
      rest = parts.join('\n').trim().slice(0, 2000);
    }

    return { verdict, bias, bullets, levels, rest };
  } catch {
    return safeDefaults();
  }
}

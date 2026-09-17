'use client';

import type { ReactNode } from 'react';

/**
 * Minimal, dependency-free markdown renderer for assistant replies.
 *
 * Supports: fenced code blocks, tables, headings, bullet/numbered lists,
 * bold (`**x**`) and inline code. Everything is emitted as React nodes, so
 * escaping is handled by React — never `dangerouslySetInnerHTML`.
 */

export type MarkdownBlock =
  | { kind: 'code'; lang: string; code: string }
  | { kind: 'table'; header: string[]; rows: string[][] }
  | { kind: 'list'; ordered: boolean; items: string[] }
  | { kind: 'heading'; level: number; text: string }
  | { kind: 'paragraph'; text: string };

function isTableSeparator(line: string): boolean {
  const s = line.trim();
  if (!s || !s.includes('-')) return false;
  return /^\|?[\s:|-]+\|?$/.test(s);
}

function splitRow(line: string): string[] {
  let s = line.trim();
  if (s.startsWith('|')) s = s.slice(1);
  if (s.endsWith('|')) s = s.slice(0, -1);
  return s.split('|').map((cell) => cell.trim());
}

const BULLET_RE = /^\s*[-*+]\s+(.*)$/;
const NUMBERED_RE = /^\s*\d+[.)]\s+(.*)$/;
const FENCE_RE = /^```([\w+-]*)\s*$/;
const HEADING_RE = /^(#{1,4})\s+(.*)$/;

function startsBlock(line: string, next: string | undefined): boolean {
  if (FENCE_RE.test(line.trim())) return true;
  if (HEADING_RE.test(line)) return true;
  if (BULLET_RE.test(line) || NUMBERED_RE.test(line)) return true;
  if (line.includes('|') && next !== undefined && isTableSeparator(next)) return true;
  return false;
}

export function parseMarkdown(source: string): MarkdownBlock[] {
  const lines = (source ?? '').replace(/\r\n?/g, '\n').split('\n');
  const blocks: MarkdownBlock[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }

    const fence = line.trim().match(FENCE_RE);
    if (fence) {
      const code: string[] = [];
      i += 1;
      while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) {
        code.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) i += 1;
      blocks.push({ kind: 'code', lang: fence[1] || '', code: code.join('\n') });
      continue;
    }

    if (line.includes('|') && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
      const header = splitRow(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].trim() && lines[i].includes('|')) {
        rows.push(splitRow(lines[i]));
        i += 1;
      }
      blocks.push({ kind: 'table', header, rows });
      continue;
    }

    const heading = line.match(HEADING_RE);
    if (heading) {
      blocks.push({ kind: 'heading', level: heading[1].length, text: heading[2] });
      i += 1;
      continue;
    }

    const bullet = line.match(BULLET_RE);
    const numbered = line.match(NUMBERED_RE);
    if (bullet || numbered) {
      const ordered = !bullet;
      const items: string[] = [];
      while (i < lines.length) {
        const b = lines[i].match(BULLET_RE);
        const n = lines[i].match(NUMBERED_RE);
        if (!b && !n) break;
        items.push(b ? b[1] : (n as RegExpMatchArray)[1]);
        i += 1;
      }
      blocks.push({ kind: 'list', ordered, items });
      continue;
    }

    const paragraph: string[] = [line];
    i += 1;
    while (i < lines.length && lines[i].trim() && !startsBlock(lines[i], lines[i + 1])) {
      paragraph.push(lines[i]);
      i += 1;
    }
    blocks.push({ kind: 'paragraph', text: paragraph.join('\n') });
  }

  return blocks;
}

const INLINE_RE = /(`[^`]+`|\*\*[^*]+\*\*)/g;

export function renderInline(text: string, keyPrefix = 'inline'): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  INLINE_RE.lastIndex = 0;

  while ((match = INLINE_RE.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const token = match[0];
    if (token.startsWith('`')) {
      nodes.push(
        <code
          key={`${keyPrefix}-${key++}`}
          className="mono"
          style={{
            background: 'var(--ds-inset-2)',
            border: '1px solid var(--ds-border)',
            borderRadius: 4,
            padding: '0 3px',
            fontSize: 11.5,
          }}
        >
          {token.slice(1, -1)}
        </code>,
      );
    } else {
      nodes.push(<strong key={`${keyPrefix}-${key++}`}>{token.slice(2, -2)}</strong>);
    }
    last = match.index + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

export function MarkdownMessage({ content }: { content: string }) {
  const blocks = parseMarkdown(content);

  return (
    <div style={{ display: 'grid', gap: 6 }}>
      {blocks.map((block, i) => {
        if (block.kind === 'code') {
          return (
            <pre
              key={`b-${i}`}
              className="mono"
              style={{
                margin: 0,
                padding: '8px 10px',
                background: 'var(--ds-inset)',
                border: '1px solid var(--ds-border)',
                borderRadius: 8,
                overflowX: 'auto',
                fontSize: 11.5,
                lineHeight: 1.5,
              }}
            >
              <code>{block.code}</code>
            </pre>
          );
        }

        if (block.kind === 'table') {
          return (
            <div key={`b-${i}`} style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr className="muted" style={{ textAlign: 'left' }}>
                    {block.header.map((cell, c) => (
                      <th
                        key={`h-${c}`}
                        style={{
                          padding: '4px 6px',
                          borderBottom: '1px solid var(--ds-border-strong)',
                        }}
                      >
                        {renderInline(cell, `h-${i}-${c}`)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {block.rows.map((row, r) => (
                    <tr key={`r-${r}`} style={{ borderTop: '1px solid var(--ds-border)' }}>
                      {row.map((cell, c) => (
                        <td key={`c-${c}`} style={{ padding: '4px 6px' }}>
                          {renderInline(cell, `c-${i}-${r}-${c}`)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }

        if (block.kind === 'list') {
          const items = block.items.map((item, n) => (
            <li key={`li-${n}`}>{renderInline(item, `li-${i}-${n}`)}</li>
          ));
          return orderedList(block.ordered, items, `b-${i}`);
        }

        if (block.kind === 'heading') {
          return (
            <div
              key={`b-${i}`}
              style={{ fontWeight: 700, fontSize: block.level <= 2 ? 14 : 13 }}
            >
              {renderInline(block.text, `hd-${i}`)}
            </div>
          );
        }

        return (
          <p key={`b-${i}`} style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
            {renderInline(block.text, `p-${i}`)}
          </p>
        );
      })}
    </div>
  );
}

function orderedList(ordered: boolean, items: ReactNode[], key: string) {
  const style = { margin: 0, paddingLeft: 18, display: 'grid', gap: 2 } as const;
  return ordered ? (
    <ol key={key} style={style}>
      {items}
    </ol>
  ) : (
    <ul key={key} style={style}>
      {items}
    </ul>
  );
}

export default MarkdownMessage;

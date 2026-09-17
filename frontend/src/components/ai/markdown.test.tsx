// @vitest-environment happy-dom
import React from 'react';
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MarkdownMessage, parseMarkdown } from './markdown';

afterEach(() => cleanup());

describe('parseMarkdown', () => {
  it('groups fenced code blocks with their language', () => {
    const blocks = parseMarkdown('Before\n\n```python\nprint(1)\n```\nAfter');
    expect(blocks).toEqual([
      { kind: 'paragraph', text: 'Before' },
      { kind: 'code', lang: 'python', code: 'print(1)' },
      { kind: 'paragraph', text: 'After' },
    ]);
  });

  it('parses tables with a separator row', () => {
    const blocks = parseMarkdown('| Leg | Strike |\n| --- | ---: |\n| BUY | 25000 |');
    expect(blocks).toEqual([
      {
        kind: 'table',
        header: ['Leg', 'Strike'],
        rows: [['BUY', '25000']],
      },
    ]);
  });

  it('does not treat a lone pipe as a table', () => {
    expect(parseMarkdown('a | b')).toEqual([{ kind: 'paragraph', text: 'a | b' }]);
  });

  it('keeps list and heading blocks', () => {
    expect(parseMarkdown('# Title')).toEqual([{ kind: 'heading', level: 1, text: 'Title' }]);
    expect(parseMarkdown('- one\n- two')).toEqual([
      { kind: 'list', ordered: false, items: ['one', 'two'] },
    ]);
    expect(parseMarkdown('1. one\n2. two')).toEqual([
      { kind: 'list', ordered: true, items: ['one', 'two'] },
    ]);
  });
});

describe('MarkdownMessage', () => {
  it('renders bold and inline code as elements (no raw markup)', () => {
    const { container } = render(<MarkdownMessage content={'**bold** and `code`'} />);
    expect(container.querySelector('strong')?.textContent).toBe('bold');
    expect(container.querySelector('code')?.textContent).toBe('code');
    expect(container.textContent).not.toContain('**');
  });

  it('renders code fences in a pre block', () => {
    render(<MarkdownMessage content={'```\nconst x = 1;\n```'} />);
    expect(screen.getByText('const x = 1;')).toBeTruthy();
  });

  it('renders tables', () => {
    render(<MarkdownMessage content={'| a | b |\n| --- | --- |\n| 1 | 2 |'} />);
    expect(screen.getByRole('table')).toBeTruthy();
    expect(screen.getByText('a')).toBeTruthy();
    expect(screen.getByText('2')).toBeTruthy();
  });

  it('never injects raw HTML from model output', () => {
    const { container } = render(
      <MarkdownMessage content={'<script>alert(1)</script> <img src=x onerror=alert(1)>'} />,
    );
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).toContain('<script>alert(1)</script>');
  });
});

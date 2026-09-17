// @vitest-environment happy-dom
import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { apiMock } = vi.hoisted(() => ({ apiMock: { streamAIChat: vi.fn() } }));
vi.mock('@/lib/api', () => ({ api: apiMock }));

import type { AIChatStreamChunk } from '@/lib/types';
import { DEFAULT_SETTINGS } from '@/lib/settingsDefaults';
import { AICopilotChat } from './AICopilotChat';

interface StreamHandlers {
  chunk: (chunk: AIChatStreamChunk) => void;
  error: (message: string) => void;
  done: () => void;
  signal?: AbortSignal;
}

let handlers: StreamHandlers;

beforeEach(() => {
  window.localStorage.clear();
  window.localStorage.setItem(
    'droid_app_settings_v2',
    JSON.stringify({ schemaVersion: 2, ai: { ...DEFAULT_SETTINGS.ai, openRouterApiKey: 'test-key' } }),
  );
  apiMock.streamAIChat.mockReset();
  apiMock.streamAIChat.mockImplementation(
    (_payload: unknown, chunk: StreamHandlers['chunk'], error: StreamHandlers['error'], done: StreamHandlers['done'], signal?: AbortSignal) => {
      handlers = { chunk, error, done, signal };
    },
  );
});

afterEach(() => cleanup());

function typeAndSend(text: string) {
  const box = screen.getByLabelText('Ask AI Copilot');
  fireEvent.change(box, { target: { value: text } });
  fireEvent.keyDown(box, { key: 'Enter' });
  return box;
}

describe('AICopilotChat', () => {
  it('streams a reply and renders markdown without raw markers', () => {
    render(<AICopilotChat symbol="NIFTY 50" />);
    typeAndSend('Is the breakout real?');

    expect(apiMock.streamAIChat).toHaveBeenCalledTimes(1);
    const payload = apiMock.streamAIChat.mock.calls[0][0] as { messages: { role: string; content: string }[] };
    expect(payload.messages[payload.messages.length - 1]).toEqual({
      role: 'user',
      content: 'Is the breakout real?',
    });

    act(() => handlers.chunk({ type: 'content', delta: '**Yes** — with a stop' }));
    expect(screen.getByText('Yes').tagName).toBe('STRONG');
    expect(screen.queryByText(/\*\*/)).toBeNull();

    act(() => handlers.done());
    expect(screen.getByRole('button', { name: 'Send' })).toBeTruthy();
  });

  it('blocks a second send while a stream is in flight', () => {
    render(<AICopilotChat symbol="NIFTY" />);
    typeAndSend('first');
    typeAndSend('second');
    expect(apiMock.streamAIChat).toHaveBeenCalledTimes(1);
  });

  it('does not send on Shift+Enter and shows suggestion chips on the empty state', () => {
    render(<AICopilotChat symbol="NIFTY" />);
    const box = screen.getByLabelText('Ask AI Copilot');
    fireEvent.change(box, { target: { value: 'draft' } });
    fireEvent.keyDown(box, { key: 'Enter', shiftKey: true });
    expect(apiMock.streamAIChat).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Where are the key options walls?' }));
    expect((screen.getByLabelText('Ask AI Copilot') as HTMLTextAreaElement).value).toBe(
      'Where are the key options walls?',
    );
  });

  it('marks partial output as stopped when the user aborts', () => {
    render(<AICopilotChat symbol="NIFTY" />);
    typeAndSend('go');
    act(() => handlers.chunk({ type: 'content', delta: 'partial answer' }));

    const signal = handlers.signal;
    fireEvent.click(screen.getByRole('button', { name: 'Stop' }));
    expect(signal?.aborted).toBe(true);

    act(() => handlers.done());
    expect(screen.getByText('Stopped — partial response shown above.')).toBeTruthy();
    expect(screen.getByText('STOPPED')).toBeTruthy();
  });

  it('shows provider errors in an assertive region, not an empty state', () => {
    render(<AICopilotChat symbol="NIFTY" />);
    typeAndSend('go');
    act(() => handlers.error('Server error 500: provider down'));

    const alert = screen.getByRole('alert');
    expect(alert.textContent).toContain('Server error 500: provider down');
    expect(screen.getByText('go')).toBeTruthy();
  });

  it('flags an empty provider response as an error', () => {
    render(<AICopilotChat symbol="NIFTY" />);
    typeAndSend('go');
    act(() => handlers.done());
    expect(screen.getByRole('alert').textContent).toContain('empty response');
  });

  it('aborts the stream on unmount', () => {
    const { unmount } = render(<AICopilotChat symbol="NIFTY" />);
    typeAndSend('go');
    const signal = handlers.signal;
    unmount();
    expect(signal?.aborted).toBe(true);
  });
});

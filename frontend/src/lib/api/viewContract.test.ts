import { describe, expect, it } from 'vitest';
import fixture from './__fixtures__/commandView.sample.json';
import {
  COMMAND_SECTION_ENVELOPE_KEYS,
  COMMAND_VIEW_SECTIONS,
  CommandSectionEnvelopeSchema,
  CommandViewSchema,
  StreamFrameSchema,
  parseCommandView,
  parseHeartbeatFrame,
  parseHintClearedFrame,
  parseHintRaisedFrame,
  parseSignalEventFrame,
  parseStreamFrame,
  parseViewSectionChangedFrame,
} from './view';

const ENVELOPE_KEYS = ['value', 'updated_at', 'freshness_s', 'degraded', 'version'];

const BASE_FRAME = {
  event: 'heartbeat',
  data: { status: 'ok' },
  priority: 'P2',
  seq: 12,
  timestamp: 1789716120000,
};

describe('CommandView fixture contract', () => {
  it('parses the frozen sample fixture', () => {
    const parsed = parseCommandView(fixture);
    expect(parsed).not.toBeNull();
    expect(parsed?.view).toBe('command');
    expect(parsed?.view_version).toBe(1);
  });

  it('covers every frozen section key', () => {
    expect(Object.keys(fixture.sections).sort()).toEqual([...COMMAND_VIEW_SECTIONS].sort());
    expect([...COMMAND_SECTION_ENVELOPE_KEYS].sort()).toEqual([...ENVELOPE_KEYS].sort());
  });

  it('gives every section all five envelope keys', () => {
    for (const [name, section] of Object.entries(fixture.sections)) {
      expect(Object.keys(section).sort(), `section ${name}`).toEqual([...ENVELOPE_KEYS].sort());
    }
  });

  it('rejects a non-numeric envelope version', () => {
    const malformed = {
      value: { fii_dii: null },
      updated_at: '2026-09-18T07:22:01.412306+00:00',
      freshness_s: 0,
      degraded: false,
      version: '3',
    };
    expect(CommandSectionEnvelopeSchema.safeParse(malformed).success).toBe(false);
  });

  it('rejects a CommandView with a wrong view literal', () => {
    expect(CommandViewSchema.safeParse({ ...fixture, view: 'dashboard' }).success).toBe(false);
  });
});

describe('stream frame contract', () => {
  it('parses a minimal frame', () => {
    expect(parseStreamFrame(BASE_FRAME)).not.toBeNull();
  });

  it('rejects a frame missing seq', () => {
    const { seq: _seq, ...missingSeq } = BASE_FRAME;
    expect(StreamFrameSchema.safeParse(missingSeq).success).toBe(false);
  });

  it('rejects a frame with an unknown priority', () => {
    expect(StreamFrameSchema.safeParse({ ...BASE_FRAME, priority: 'P3' }).success).toBe(false);
  });

  it('rejects a frame with a non-numeric seq', () => {
    expect(StreamFrameSchema.safeParse({ ...BASE_FRAME, seq: '12' }).success).toBe(false);
  });

  it('parses a view.section.changed frame and rejects a mismatched event', () => {
    const frame = {
      event: 'view.section.changed',
      data: {
        section: 'market',
        version: 2,
        value: { active: false, reason: null },
        updated_at: '2026-09-18T07:22:01.412306+00:00',
        freshness_s: 0,
        degraded: false,
      },
      priority: 'P0',
      seq: 42,
      timestamp: 1789716120000,
    };
    expect(parseViewSectionChangedFrame(frame)?.data.section).toBe('market');
    expect(parseHeartbeatFrame(frame)).toBeNull();
  });

  it('parses a signal.event frame', () => {
    const frame = {
      event: 'signal.event',
      data: {
        event: 'SIGNAL_CREATED',
        data: { id: 'SIG-20260918-0007', underlying: 'NIFTY' },
        priority: 'P0',
        seq: 901,
        timestamp: 1789716120000,
      },
      priority: 'P1',
      seq: 43,
      timestamp: 1789716120000,
    };
    expect(parseSignalEventFrame(frame)?.data.event).toBe('SIGNAL_CREATED');
    expect(parseStreamFrame(frame)?.event).toBe('signal.event');
  });

  it('parses a heartbeat frame', () => {
    expect(parseHeartbeatFrame(BASE_FRAME)?.data.status).toBe('ok');
  });

  it('parses hint.raised and hint.cleared frames', () => {
    const raised = {
      event: 'hint.raised',
      data: { hint: { id: 'feed:stale:SENSEX', severity: 'warn', action_required: false, target: 'feed_health' } },
      priority: 'P1',
      seq: 44,
      timestamp: 1789716120000,
    };
    const cleared = {
      event: 'hint.cleared',
      data: { id: 'feed:stale:SENSEX' },
      priority: 'P1',
      seq: 45,
      timestamp: 1789716120000,
    };
    expect(parseHintRaisedFrame(raised)?.data.hint.id).toBe('feed:stale:SENSEX');
    expect(parseHintClearedFrame(cleared)?.data.id).toBe('feed:stale:SENSEX');
    expect(parseHintRaisedFrame(cleared)).toBeNull();
  });
});

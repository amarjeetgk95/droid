import { describe, expect, it, vi } from 'vitest';
import { scalpAudio, playScalpAudio, type AudioCueType } from './scalpAudio';

describe('scalpAudio engine', () => {
  it('toggles enabled state and notifies subscribers', () => {
    const subscriber = vi.fn();
    const unsub = scalpAudio.subscribe(subscriber);

    scalpAudio.setEnabled(false);
    expect(scalpAudio.isEnabled()).toBe(false);
    expect(subscriber).toHaveBeenCalledWith(false);

    scalpAudio.setEnabled(true);
    expect(scalpAudio.isEnabled()).toBe(true);
    expect(subscriber).toHaveBeenCalledWith(true);

    unsub();
  });

  it('tolerates non-browser execution for all cue types without throwing', () => {
    const cues: AudioCueType[] = [
      'enter',
      'panic',
      'limit',
      'target',
      'stop',
      'kill',
      'confirmed',
    ];

    for (const cue of cues) {
      expect(() => playScalpAudio(cue)).not.toThrow();
    }
  });

  it('exposes helper methods for cues', () => {
    expect(() => scalpAudio.target()).not.toThrow();
    expect(() => scalpAudio.stop()).not.toThrow();
    expect(() => scalpAudio.kill()).not.toThrow();
    expect(() => scalpAudio.confirmed()).not.toThrow();
    expect(() => scalpAudio.enter()).not.toThrow();
    expect(() => scalpAudio.panic()).not.toThrow();
    expect(() => scalpAudio.limit()).not.toThrow();
  });
});

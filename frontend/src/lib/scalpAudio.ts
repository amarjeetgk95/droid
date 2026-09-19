'use client';

export type AudioCueType =
  | 'enter'
  | 'panic'
  | 'limit'
  | 'target'
  | 'stop'
  | 'kill'
  | 'confirmed';

let sharedScalpAudioCtx: AudioContext | null = null;
const AUDIO_PREF_KEY = 'droid_audio_enabled';

const listeners = new Set<(enabled: boolean) => void>();

function readInitialPref(): boolean {
  if (typeof window === 'undefined') return true;
  try {
    const val = localStorage.getItem(AUDIO_PREF_KEY);
    return val === null ? true : val === 'true';
  } catch {
    return true;
  }
}

let scalpAudioEnabled = readInitialPref();

export function getScalpAudioCtx(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  try {
    const AudioCtx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) return null;
    if (!sharedScalpAudioCtx || sharedScalpAudioCtx.state === 'closed') {
      sharedScalpAudioCtx = new AudioCtx();
    }
    if (sharedScalpAudioCtx.state === 'suspended') {
      void sharedScalpAudioCtx.resume().catch(() => undefined);
    }
    return sharedScalpAudioCtx;
  } catch {
    return null;
  }
}

export function playScalpAudio(type: AudioCueType): void {
  if (!scalpAudioEnabled) return;
  try {
    const ctx = getScalpAudioCtx();
    if (!ctx) return;
    const now = ctx.currentTime;

    if (type === 'target') {
      // Ascending major third chime: C6 (1046.5Hz) -> E6 (1318.5Hz)
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(1046.5, now);
      osc.frequency.setValueAtTime(1318.5, now + 0.08);
      gain.gain.setValueAtTime(0.18, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.35);
    } else if (type === 'stop') {
      // Soft descending tone: 440Hz -> 261Hz
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(440, now);
      osc.frequency.exponentialRampToValueAtTime(261.6, now + 0.2);
      gain.gain.setValueAtTime(0.2, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.3);
    } else if (type === 'confirmed') {
      // Crisp bell ping: D6 (1174.7Hz)
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(1174.66, now);
      gain.gain.setValueAtTime(0.15, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.22);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.22);
    } else if (type === 'kill') {
      // Double warning pulse: 880Hz sawtooth
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(880, now);
      gain.gain.setValueAtTime(0.22, now);
      gain.gain.setValueAtTime(0.001, now + 0.08);
      gain.gain.setValueAtTime(0.22, now + 0.12);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.28);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.28);
    } else if (type === 'enter') {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(587.33, now); // D5
      osc.frequency.exponentialRampToValueAtTime(880.0, now + 0.15); // A5
      gain.gain.setValueAtTime(0.2, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.35);
    } else if (type === 'panic') {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(440, now);
      osc.frequency.setValueAtTime(220, now + 0.15);
      gain.gain.setValueAtTime(0.25, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.4);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.4);
    } else if (type === 'limit') {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(370, now);
      osc.frequency.setValueAtTime(290, now + 0.1);
      gain.gain.setValueAtTime(0.18, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.25);
    }
  } catch {
    // Audio context may be restricted before user gesture or unavailable in environment
  }
}

export const scalpAudio = {
  enter: () => playScalpAudio('enter'),
  panic: () => playScalpAudio('panic'),
  limit: () => playScalpAudio('limit'),
  target: () => playScalpAudio('target'),
  stop: () => playScalpAudio('stop'),
  kill: () => playScalpAudio('kill'),
  confirmed: () => playScalpAudio('confirmed'),
  setEnabled: (enabled: boolean) => {
    scalpAudioEnabled = enabled;
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(AUDIO_PREF_KEY, String(enabled));
      } catch {
        // storage disabled
      }
    }
    listeners.forEach((fn) => {
      try {
        fn(enabled);
      } catch {
        // ignore subscriber error
      }
    });
  },
  isEnabled: () => scalpAudioEnabled,
  subscribe: (fn: (enabled: boolean) => void) => {
    listeners.add(fn);
    return () => {
      listeners.delete(fn);
    };
  },
};

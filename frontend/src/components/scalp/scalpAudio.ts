'use client';

let sharedScalpAudioCtx: AudioContext | null = null;
let scalpAudioEnabled = true;

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

export function playScalpAudio(type: 'enter' | 'panic' | 'limit'): void {
  if (!scalpAudioEnabled) return;
  try {
    const ctx = getScalpAudioCtx();
    if (!ctx) return;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);

    if (type === 'enter') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
      osc.frequency.exponentialRampToValueAtTime(880.0, ctx.currentTime + 0.15); // A5
      gain.gain.setValueAtTime(0.2, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
      osc.start();
      osc.stop(ctx.currentTime + 0.35);
    } else if (type === 'panic') {
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(440, ctx.currentTime);
      osc.frequency.setValueAtTime(220, ctx.currentTime + 0.15);
      gain.gain.setValueAtTime(0.25, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
      osc.start();
      osc.stop(ctx.currentTime + 0.4);
    } else if (type === 'limit') {
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(370, ctx.currentTime);
      osc.frequency.setValueAtTime(290, ctx.currentTime + 0.1);
      gain.gain.setValueAtTime(0.18, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
      osc.start();
      osc.stop(ctx.currentTime + 0.25);
    }
  } catch {
    // Audio context may be restricted before user gesture or unavailable in environment
  }
}

export const scalpAudio = {
  enter: () => playScalpAudio('enter'),
  panic: () => playScalpAudio('panic'),
  limit: () => playScalpAudio('limit'),
  setEnabled: (enabled: boolean) => {
    scalpAudioEnabled = enabled;
  },
  isEnabled: () => scalpAudioEnabled,
};

// Shared AudioContext — created once, reused for every chime (no per-alert leak)
let sharedAudioCtx: AudioContext | null = null;

export function playAlertChime(isWin = false, isScalp = false) {
  if (typeof window === 'undefined') return;
  try {
    const AC = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AC) return;
    if (!sharedAudioCtx || sharedAudioCtx.state === 'closed') {
      sharedAudioCtx = new AC();
    }
    const ctx = sharedAudioCtx;
    if (ctx.state === 'suspended') void ctx.resume();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    if (isScalp) {
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(880.0, ctx.currentTime);
      osc.frequency.setValueAtTime(1174.66, ctx.currentTime + 0.08);
      gain.gain.setValueAtTime(0.18, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
    } else {
      osc.type = isWin ? 'triangle' : 'sine';
      osc.frequency.setValueAtTime(isWin ? 587.33 : 440.0, ctx.currentTime);
      if (isWin) {
        osc.frequency.exponentialRampToValueAtTime(880.0, ctx.currentTime + 0.15);
      } else {
        osc.frequency.exponentialRampToValueAtTime(659.25, ctx.currentTime + 0.12);
      }
      gain.gain.setValueAtTime(0.2, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
    }

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start();
    osc.stop(ctx.currentTime + (isScalp ? 0.25 : 0.35));
    osc.onended = () => {
      try {
        osc.disconnect();
        gain.disconnect();
      } catch {}
    };
  } catch {}
}

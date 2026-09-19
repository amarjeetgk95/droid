'use client';

import { useEffect, useState } from 'react';
import { Volume2, VolumeX } from 'lucide-react';
import { scalpAudio } from '@/lib/scalpAudio';

export function AudioControl() {
  const [enabled, setEnabled] = useState(() => scalpAudio.isEnabled());

  useEffect(() => {
    return scalpAudio.subscribe((next) => {
      setEnabled(next);
    });
  }, []);

  const toggle = () => {
    const next = !enabled;
    scalpAudio.setEnabled(next);
    if (next) {
      scalpAudio.confirmed();
    }
  };

  return (
    <button
      type="button"
      onClick={toggle}
      className={`btn icon-btn ${enabled ? 'text-primary' : 'text-muted-foreground opacity-60'}`}
      title={enabled ? 'Audio alerts active (click to mute)' : 'Audio alerts muted (click to enable)'}
      aria-label={enabled ? 'Mute audio alerts' : 'Enable audio alerts'}
    >
      {enabled ? <Volume2 size={15} /> : <VolumeX size={15} />}
    </button>
  );
}

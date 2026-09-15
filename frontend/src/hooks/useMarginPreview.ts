'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';

export interface MarginPreviewInfo {
  required: number;
  affordable: boolean;
}

export function useMarginPreview(
  underlying: string,
  symbol: string | null,
  quantity: number,
  price: number | null
): MarginPreviewInfo | null {
  const [marginInfo, setMarginInfo] = useState<MarginPreviewInfo | null>(null);

  useEffect(() => {
    if (!symbol || !price || !(price > 0) || quantity <= 0) {
      setMarginInfo(null);
      return;
    }

    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const res = await api.previewPaperMargin({
          symbol,
          underlying,
          side: 'BUY',
          quantity,
          price,
        });

        if (cancelled) return;
        if (!res.error && res.data) {
          setMarginInfo({
            required: res.data.required_margin,
            affordable: res.data.affordable,
          });
        }
      } catch {
        if (!cancelled) setMarginInfo(null);
      }
    }, 600);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [underlying, symbol, quantity, price]);

  return marginInfo;
}

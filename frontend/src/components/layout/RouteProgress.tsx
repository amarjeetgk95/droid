'use client';

import { useEffect, useState, useRef } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import { navigationController } from '@/lib/navigationController';

/**
 * RouteProgress
 *
 * 2px high-performance top progress bar.
 * Provides immediate tactile visual confirmation of navigation intent across
 * all links, buttons, and keyboard shortcuts without causing layout displacement.
 */
export function RouteProgress() {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [visible, setVisible] = useState(false);
  const [progress, setProgress] = useState(0);

  const prevPathRef = useRef(pathname);
  const prevParamsRef = useRef(searchParams?.toString());
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Subscribe to navigationController
  useEffect(() => {
    return navigationController.subscribe((state) => {
      if (state.isNavigating) {
        if (timerRef.current) clearTimeout(timerRef.current);
        setVisible(true);
        setProgress(30);

        // Advance gradually while awaiting page chunk
        timerRef.current = setTimeout(() => {
          setProgress(70);
        }, 150);
      } else {
        // Complete
        setProgress(100);
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(() => {
          setVisible(false);
          setProgress(0);
        }, 250);
      }
    });
  }, []);

  // When pathname or search params change, complete navigation
  useEffect(() => {
    const currentParams = searchParams?.toString();
    if (pathname !== prevPathRef.current || currentParams !== prevParamsRef.current) {
      prevPathRef.current = pathname;
      prevParamsRef.current = currentParams;
      navigationController.complete();
    }
  }, [pathname, searchParams]);

  if (!visible && progress === 0) return null;

  return (
    <div
      aria-hidden="true"
      className="fixed top-0 left-0 right-0 z-[100] h-[2px] pointer-events-none bg-transparent overflow-hidden"
    >
      <div
        className="h-full bg-primary transition-all duration-200 ease-out shadow-[0_0_8px_rgba(37,99,235,0.6)]"
        style={{
          width: `${progress}%`,
          opacity: visible ? 1 : 0,
          transitionProperty: 'width, opacity',
        }}
      />
    </div>
  );
}

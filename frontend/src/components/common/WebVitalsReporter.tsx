'use client';

import { useReportWebVitals } from 'next/web-vitals';
import { reportWebVital } from '@/lib/telemetry';

/** Mount once in the root layout — forwards real-user vitals into the telemetry buffer. */
export function WebVitalsReporter() {
  useReportWebVitals((metric) => {
    reportWebVital({ name: metric.name, value: metric.value, rating: metric.rating });
  });
  return null;
}

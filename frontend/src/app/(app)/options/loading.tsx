import { OptionChainSkeleton } from '@/components/options/OptionChainSkeleton';

/**
 * Route-level loading boundary for Options Desk (/options).
 * Matches the exact 13-column geometry of the live Option Chain matrix.
 */
export default function OptionsLoading() {
  return <OptionChainSkeleton rows={12} />;
}

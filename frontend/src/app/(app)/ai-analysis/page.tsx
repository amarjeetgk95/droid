'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Brain, ArrowRight } from 'lucide-react';
import Link from 'next/link';

export default function AIAnalysisRedirectPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace('/ai-command-center?tab=research');
  }, [router]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] gap-3 text-center p-6">
      <div className="p-3 bg-primary/10 rounded-2xl text-primary animate-pulse">
        <Brain className="w-8 h-8" />
      </div>
      <h2 className="text-lg font-bold text-foreground">Moving to AI Command Center</h2>
      <p className="text-xs text-muted-foreground max-w-sm">
        AI Research and AI Live Calls have been unified into a single AI Command Center.
      </p>
      <Link
        href="/ai-command-center?tab=research"
        className="mt-2 inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 transition-all cursor-pointer shadow-xs"
      >
        <span>Open AI Command Center</span>
        <ArrowRight className="w-3.5 h-3.5" />
      </Link>
    </div>
  );
}

import { redirect } from 'next/navigation';

/**
 * System Nerve is consolidated under Terminal Configuration at /settings?tab=system.
 * Redirects immediately so any legacy links, bookmarks, or bottom-nav clicks land directly on the system tab.
 */
export default function SystemPage() {
  redirect('/settings?tab=system');
}

import { redirect } from 'next/navigation';

/** Genuine alias — the Research Lab lives at /lab. Server-side redirect, no client mount. */
export default function ResearchAliasPage() {
  redirect('/lab');
}

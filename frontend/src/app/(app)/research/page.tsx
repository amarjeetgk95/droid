import { permanentRedirect } from 'next/navigation';

/** Genuine alias — the Research Lab lives at /lab. Permanent server-side redirect, no client mount. */
export default function ResearchAliasPage() {
  permanentRedirect('/lab');
}

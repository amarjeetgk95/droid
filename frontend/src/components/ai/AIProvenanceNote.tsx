'use client';

/**
 * Consistent provenance / disclaimer label for every AI output surface.
 * AI content is generated, possibly wrong, and never financial advice.
 */
export function AIProvenanceNote({
  provider,
  note,
  contextPage,
}: {
  provider?: string | null;
  note?: string | null;
  contextPage?: string;
}) {
  const parts = ['AI-generated'];
  if (provider) parts.push(`via ${provider}`);
  parts.push('verify before acting · not financial advice');
  return (
    <p className="faint" style={{ fontSize: 11, margin: 0 }}>
      {parts.join(' · ')}
      {note ? ` · ${note}` : ''}
      {contextPage ? ` · ${contextPage}` : ''}
    </p>
  );
}

export default AIProvenanceNote;

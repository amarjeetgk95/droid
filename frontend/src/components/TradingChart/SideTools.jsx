import React from 'react';

const TOOLS = [
  { t: 'Cross', i: '✛' },
  { t: 'Trend line', i: '╱' },
  { t: 'Horizontal line', i: '━' },
  { t: 'Rectangle', i: '▭' },
  { t: 'Text', i: 'T' },
  { t: 'Measure', i: '⇕' },
];

export default function SideTools({ onSelect }) {
  return (
    <aside className="w-[46px] border-r border-[#e0e3eb] bg-white flex flex-col items-center py-2 gap-1 shrink-0">
      {TOOLS.map(({ t, i }) => (
        <button key={t} className="tc-tool" title={t} onClick={() => onSelect?.(t)}>
          {i}
        </button>
      ))}
      <button className="mt-auto tc-tool" title="Settings" onClick={() => onSelect?.('Settings')}>
        ⚙
      </button>
    </aside>
  );
}

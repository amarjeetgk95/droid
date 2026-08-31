import React from 'react';
import { COLORS, TIMEFRAMES, CHART_TYPES } from './constants';
import { fmtP } from './utils';

export default function TopBar({
  symbol = 'BTCUSDT',
  exchangeLabel = 'Binance · Crypto',
  tf,
  setTf,
  chartType,
  setChartType,
  live,
  setLive,
  lastPrice,
  changePct,
  onReset,
}) {
  const up = changePct >= 0;

  return (
    <header className="h-[42px] flex items-center gap-1 px-2 border-b border-[#e0e3eb] bg-white shrink-0 text-[#131722]">
      <div className="flex items-center gap-2 pr-3 border-r border-[#e0e3eb]">
        <div className="w-7 h-7 rounded-full bg-[#2962ff] grid place-items-center text-[13px] font-bold text-white">
          ₿
        </div>
        <div className="leading-tight">
          <div className="text-[14px] font-semibold text-[#131722]">{symbol}</div>
          <div className="text-[10px] text-[#6a6d78] -mt-[2px]">{exchangeLabel}</div>
        </div>
      </div>

      <div className="flex items-center gap-[2px] px-2 border-r border-[#e0e3eb]">
        {TIMEFRAMES.map(({ label, value }) => (
          <button
            key={value}
            className={'tc-tf-btn' + (tf === value ? ' active' : '')}
            onClick={() => setTf(value)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-[2px] px-2 border-r border-[#e0e3eb]">
        {CHART_TYPES.map((t) => (
          <button
            key={t}
            className={'tc-tf-btn' + (chartType === t ? ' active' : '')}
            onClick={() => setChartType(t)}
          >
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-[2px] px-2">
        <button className={'tc-tf-btn' + (live ? ' active' : '')} onClick={() => setLive((v) => !v)}>
          <span className={'tc-dot' + (live ? ' on' : '')} />
          Live
        </button>
      </div>

      <div className="ml-auto flex items-center gap-2 pr-1">
        <span className="text-[15px] font-semibold" style={{ color: up ? COLORS.up : COLORS.down }}>
          {fmtP(lastPrice)}
        </span>
        <span
          className="tc-chip"
          style={{
            background: up ? 'rgba(38,166,154,.15)' : 'rgba(239,83,80,.15)',
            color: up ? COLORS.up : COLORS.down,
          }}
        >
          {up ? '+' : ''}
          {changePct.toFixed(2)}%
        </span>
        <button className="tc-tf-btn" onClick={onReset} title="Reset view (R)">
          Reset
        </button>
      </div>
    </header>
  );
}

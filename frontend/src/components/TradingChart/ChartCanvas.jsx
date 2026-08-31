import React, { useRef, useEffect, useCallback } from 'react';
import { COLORS, PAD_R, PAD_B, PAD_T } from './constants';
import { fmtP, fmtPrice, fmtT, fmtDay, fmtFull, niceSteps, clampStart } from './utils';

/* right-axis price tag (like TV's crosshair price label) */
function tag(ctx, x, y, text, bg, fg) {
  ctx.font = '11px sans-serif';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = bg;
  ctx.fillRect(x + 1, y - 9, PAD_R - 2, 18);
  ctx.fillStyle = fg;
  ctx.fillText(text, x + 8, y);
}

/* floating OHLC tooltip panel near the cursor — white TradingView style */
function drawTooltip(ctx, d, mx, my, plotW) {
  const rowH = 16;
  const w = 150;
  const h = 6 * rowH + 8;
  let bx = mx + 14;
  let by = my - h - 12;
  if (bx + w > plotW) bx = mx - 14 - w;
  if (by < 0) by = my + 18;

  const col = d.c >= d.o ? COLORS.up : COLORS.down;
  const delta = d.c - d.o;
  const dPct = (delta / d.o) * 100;

  ctx.fillStyle = 'rgba(255,255,255,0.98)';
  ctx.fillRect(bx, by, w, h);
  ctx.strokeStyle = '#e0e3eb';
  ctx.lineWidth = 1;
  ctx.strokeRect(bx + 0.5, by + 0.5, w - 1, h - 1);
  // subtle shadow
  ctx.fillStyle = 'rgba(0,0,0,0.06)';
  ctx.fillRect(bx + 2, by + h - 1, w - 4, 2);

  ctx.font = '11px sans-serif';
  ctx.textBaseline = 'middle';

  // time header (centered)
  ctx.fillStyle = '#131722';
  ctx.textAlign = 'center';
  ctx.fillText(fmtFull(d.t), bx + w / 2, by + 8 + rowH / 2);

  const rows = [
    { l: 'O', v: fmtP(d.o), c: col },
    { l: 'H', v: fmtP(d.h), c: col },
    { l: 'L', v: fmtP(d.l), c: col },
    { l: 'C', v: fmtP(d.c), c: col },
    { l: 'Δ', v: `${delta >= 0 ? '+' : ''}${fmtP(delta)} (${dPct >= 0 ? '+' : ''}${dPct.toFixed(2)}%)`, c: col },
  ];
  rows.forEach((r, i) => {
    const y = by + 8 + (i + 1) * rowH + rowH / 2;
    ctx.textAlign = 'left';
    ctx.fillStyle = '#6a6d78';
    ctx.fillText(r.l, bx + 8, y);
    ctx.textAlign = 'right';
    ctx.fillStyle = r.c;
    ctx.fillText(r.v, bx + w - 8, y);
  });
}

export default function ChartCanvas({
  data,
  tf,
  chartType,
  view,
  setView,
  onHover,
  onReset,
  symbol = 'BTCUSDT',
}) {
  const cvsRef = useRef(null);
  const wrapRef = useRef(null);
  const mouseRef = useRef({ x: null, y: null, inside: false });
  const dragRef = useRef(null);
  const touchRef = useRef(null);
  const plotW = useRef(0);
  const plotH = useRef(0);
  const drawRef = useRef(null);

  // refs mirroring props so stable (native) listeners always read fresh values
  const dataRef = useRef(data);
  dataRef.current = data;
  const viewRef = useRef(view);
  viewRef.current = view;

  const draw = useCallback(() => {
    const cvs = cvsRef.current;
    if (!cvs) return;
    const ctx = cvs.getContext('2d');
    const W = plotW.current + PAD_R;
    const H = plotH.current + PAD_B;
    if (W <= 0 || H <= 0 || !data.length) return;

    const s = Math.max(0, Math.floor(view.start));
    const e = Math.min(data.length, Math.ceil(view.start + view.count));
    const slice = data.slice(s, e);
    if (!slice.length) return;

    const priceTop = PAD_T;
    const priceBot = plotH.current - 6;

    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, W, H);

    let min = Infinity;
    let max = -Infinity;
    slice.forEach((d) => {
      min = Math.min(min, d.l);
      max = Math.max(max, d.h);
    });
    const pad = (max - min) * 0.08 || 1;
    min -= pad;
    max += pad;

    const barW = plotW.current / view.count;
    const xOf = (i) => (i - view.start) * barW + barW / 2;
    const yOf = (p) => priceTop + ((max - p) / (max - min)) * (priceBot - priceTop);
    const pOf = (y) => max - ((y - priceTop) / (priceBot - priceTop)) * (max - min);

    /* price grid */
    ctx.font = '11px -apple-system, sans-serif';
    ctx.textBaseline = 'middle';
    const steps = niceSteps(min, max, Math.max(3, Math.floor((priceBot - priceTop) / 56)));
    ctx.strokeStyle = COLORS.grid;
    ctx.lineWidth = 1;
    steps.forEach((p) => {
      const y = Math.round(yOf(p)) + 0.5;
      if (y < priceTop - 10 || y > priceBot) return;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(plotW.current, y);
      ctx.stroke();
      ctx.fillStyle = COLORS.text;
      ctx.textAlign = 'left';
      ctx.fillText(fmtPrice(p, min, max), plotW.current + 8, y);
    });

    /* hovered column highlight (drawn under the candles) — light theme */
    const m = mouseRef.current;
    let hoverIdx = data.length - 1;
    if (m.inside && m.x < plotW.current && m.y < plotH.current) {
      hoverIdx = Math.max(0, Math.min(data.length - 1, Math.round(view.start + (m.x - barW / 2) / barW)));
      ctx.fillStyle = 'rgba(0,0,0,0.04)';
      ctx.fillRect(xOf(hoverIdx) - barW / 2, priceTop, barW, priceBot - priceTop);
    }

    /* time grid (+ day separators when the view spans multiple days) */
    const tickEvery = Math.max(1, Math.round(view.count / 8));
    const spanDays = data[e - 1].t - data[s].t > 86400000;
    const dayOf = (t) => new Date(t).getUTCDate();
    ctx.textAlign = 'center';
    for (let i = s; i < e; i++) {
      const isTick = i % tickEvery === 0;
      const isDay = spanDays && i > s && dayOf(data[i].t) !== dayOf(data[i - 1].t);
      if (!isTick && !isDay) continue;
      const x = Math.round(xOf(i)) + 0.5;
      if (x < 0 || x > plotW.current) continue;
      ctx.strokeStyle = isDay ? COLORS.axis : COLORS.grid;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, plotH.current);
      ctx.stroke();
      if (isDay) {
        ctx.fillStyle = '#5d606b';
        ctx.fillText(fmtDay(data[i].t), x, plotH.current + 13);
      } else if (isTick) {
        ctx.fillStyle = COLORS.text;
        ctx.fillText(fmtT(data[i].t, tf), x, plotH.current + 13);
      }
    }

    /* series */
    if (chartType === 'candle') {
      const bw = Math.max(1, barW * 0.7);
      for (let i = s; i < e; i++) {
        const d = data[i];
        const up = d.c >= d.o;
        const x = xOf(i);
        ctx.strokeStyle = up ? COLORS.up : COLORS.down;
        ctx.fillStyle = up ? COLORS.up : COLORS.down;
        ctx.beginPath();
        ctx.moveTo(Math.round(x) + 0.5, yOf(d.h));
        ctx.lineTo(Math.round(x) + 0.5, yOf(d.l));
        ctx.stroke();
        const y1 = yOf(Math.max(d.o, d.c));
        const y2 = yOf(Math.min(d.o, d.c));
        if (bw <= 1.6) ctx.fillRect(Math.round(x), y1, 1, Math.max(1, y2 - y1));
        else
          ctx.fillRect(
            Math.round(x - bw / 2),
            Math.round(y1),
            Math.round(bw),
            Math.max(1, Math.round(y2 - y1))
          );
      }
    } else {
      ctx.beginPath();
      for (let i = s; i < e; i++) {
        const x = xOf(i);
        const y = yOf(data[i].c);
        i === s ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      if (chartType === 'area') {
        const g = ctx.createLinearGradient(0, priceTop, 0, priceBot);
        g.addColorStop(0, 'rgba(41,98,255,.35)');
        g.addColorStop(1, 'rgba(41,98,255,0)');
        ctx.lineTo(xOf(e - 1), priceBot);
        ctx.lineTo(xOf(s), priceBot);
        ctx.closePath();
        ctx.fillStyle = g;
        ctx.fill();
        ctx.beginPath();
        for (let i = s; i < e; i++) {
          const x = xOf(i);
          const y = yOf(data[i].c);
          i === s ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        }
      }
      ctx.strokeStyle = COLORS.line;
      ctx.lineWidth = 1.6;
      ctx.stroke();
      ctx.lineWidth = 1;
    }

    /* symbol watermark — subtle on white */
    ctx.save();
    ctx.globalAlpha = 0.06;
    ctx.font = '700 40px -apple-system, sans-serif';
    ctx.fillStyle = '#131722';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';
    const wm = symbol;
    const ww = ctx.measureText(wm).width;
    ctx.fillText(wm, plotW.current - ww - 14, priceBot - 16);
    ctx.restore();

    /* last price line */
    const last = data[data.length - 1];
    const ly = yOf(last.c);
    if (ly > priceTop && ly < priceBot) {
      ctx.setLineDash([4, 4]);
      ctx.strokeStyle = last.c >= last.o ? COLORS.up : COLORS.down;
      ctx.beginPath();
      ctx.moveTo(0, ly);
      ctx.lineTo(plotW.current, ly);
      ctx.stroke();
      ctx.setLineDash([]);
      tag(ctx, plotW.current, ly, fmtPrice(last.c, min, max), last.c >= last.o ? COLORS.up : COLORS.down, '#fff');
    }

    /* axes */
    ctx.strokeStyle = COLORS.axis;
    ctx.beginPath();
    ctx.moveTo(plotW.current + 0.5, 0);
    ctx.lineTo(plotW.current + 0.5, H);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(0, plotH.current + 0.5);
    ctx.lineTo(W, plotH.current + 0.5);
    ctx.stroke();

    /* crosshair + tooltip */
    if (m.inside && m.x < plotW.current && m.y < plotH.current) {
      const cx = Math.round(xOf(hoverIdx)) + 0.5;
      ctx.setLineDash([3, 3]);
      ctx.strokeStyle = COLORS.cross;
      ctx.beginPath();
      ctx.moveTo(cx, 0);
      ctx.lineTo(cx, plotH.current);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(0, m.y + 0.5);
      ctx.lineTo(plotW.current, m.y + 0.5);
      ctx.stroke();
      ctx.setLineDash([]);

      // axis price tag + delta from last close
      const px = pOf(m.y);
      tag(ctx, plotW.current, m.y, fmtPrice(px, min, max), '#363a45', '#d1d4dc');
      const delta = px - last.c;
      const dCol = delta >= 0 ? COLORS.up : COLORS.down;
      ctx.font = '11px sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = dCol;
      ctx.fillText(
        `${delta >= 0 ? '+' : ''}${fmtPrice(delta, min, max)} (${((delta / last.c) * 100).toFixed(2)}%)`,
        plotW.current + 8,
        m.y + 20
      );

      // time tag on the axis
      const label = fmtFull(data[hoverIdx].t);
      ctx.font = '11px sans-serif';
      const tw = ctx.measureText(label).width + 12;
      ctx.fillStyle = '#363a45';
      ctx.fillRect(cx - tw / 2, plotH.current + 2, tw, 18);
      ctx.fillStyle = '#d1d4dc';
      ctx.textAlign = 'center';
      ctx.fillText(label, cx, plotH.current + 11);

      drawTooltip(ctx, data[hoverIdx], m.x, m.y, plotW.current);
    }
    onHover(hoverIdx);
  }, [data, tf, chartType, view, onHover, symbol]);

  drawRef.current = draw; // keep latest closure reachable from stable callbacks

  useEffect(() => {
    draw();
  }, [draw]);

  // Resize observer keeps canvas crisp on container size changes
  useEffect(() => {
    const cvs = cvsRef.current;
    const wrap = wrapRef.current;
    if (!cvs || !wrap) return undefined;
    const ro = new ResizeObserver(() => {
      const r = wrap.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      plotW.current = r.width - PAD_R;
      plotH.current = r.height - PAD_B;
      cvs.width = r.width * dpr;
      cvs.height = r.height * dpr;
      cvs.style.width = r.width + 'px';
      cvs.style.height = r.height + 'px';
      cvs.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0);
      drawRef.current?.();
    });
    ro.observe(wrap);
    return () => ro.disconnect();
  }, []);

  const scheduleRedraw = useRef(0);
  const redrawNextFrame = () => {
    if (scheduleRedraw.current) return;
    scheduleRedraw.current = requestAnimationFrame(() => {
      scheduleRedraw.current = 0;
      drawRef.current?.();
    });
  };

  /* native wheel + touch (non-passive so we can preventDefault page scroll) */
  useEffect(() => {
    const cvs = cvsRef.current;
    if (!cvs) return undefined;

    const onWheel = (ev) => {
      ev.preventDefault();
      const r = cvs.getBoundingClientRect();
      const px = (ev.clientX - r.left) / plotW.current;
      const factor = ev.deltaY > 0 ? 1.12 : 0.89;
      const v = viewRef.current;
      const newCount = Math.max(20, Math.min(dataRef.current.length, v.count * factor));
      const anchor = v.start + px * v.count;
      const ns = clampStart(dataRef.current.length, newCount, anchor - px * newCount);
      setView({ count: newCount, start: ns });
      redrawNextFrame();
    };

    const onTouchStart = (ev) => {
      if (ev.touches.length === 1) {
        const t = ev.touches[0];
        touchRef.current = {
          mode: 'pan',
          x: t.clientX,
          y: t.clientY,
          start0: viewRef.current.start,
          count0: viewRef.current.count,
        };
      } else if (ev.touches.length === 2) {
        const [a, b] = ev.touches;
        const r = cvs.getBoundingClientRect();
        touchRef.current = {
          mode: 'pinch',
          dist0: Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY),
          anchorPx: ((a.clientX + b.clientX) / 2 - r.left) / plotW.current,
          start0: viewRef.current.start,
          count0: viewRef.current.count,
        };
      }
    };

    const onTouchMove = (ev) => {
      const st = touchRef.current;
      if (!st) return;
      if (ev.cancelable) ev.preventDefault();
      if (st.mode === 'pan' && ev.touches.length === 1) {
        const t = ev.touches[0];
        const dx = t.clientX - st.x;
        const barW = plotW.current / st.count0;
        setView((v) => ({ ...v, start: clampStart(dataRef.current.length, v.count, st.start0 - dx / barW) }));
      } else if (st.mode === 'pinch' && ev.touches.length === 2) {
        const [a, b] = ev.touches;
        const dist = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
        if (!dist) return;
        const factor = st.dist0 / dist;
        const newCount = Math.max(20, Math.min(dataRef.current.length, st.count0 * factor));
        const anchor = st.start0 + st.anchorPx * st.count0;
        const ns = clampStart(dataRef.current.length, newCount, anchor - st.anchorPx * newCount);
        setView({ count: newCount, start: ns });
      }
      redrawNextFrame();
    };

    const onTouchEnd = () => {
      touchRef.current = null;
    };

    cvs.addEventListener('wheel', onWheel, { passive: false });
    cvs.addEventListener('touchstart', onTouchStart, { passive: true });
    cvs.addEventListener('touchmove', onTouchMove, { passive: false });
    cvs.addEventListener('touchend', onTouchEnd);
    cvs.addEventListener('touchcancel', onTouchEnd);
    return () => {
      cvs.removeEventListener('wheel', onWheel);
      cvs.removeEventListener('touchstart', onTouchStart);
      cvs.removeEventListener('touchmove', onTouchMove);
      cvs.removeEventListener('touchend', onTouchEnd);
      cvs.removeEventListener('touchcancel', onTouchEnd);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* mouse pan */
  const onMouseMove = (ev) => {
    const r = cvsRef.current.getBoundingClientRect();
    mouseRef.current.x = ev.clientX - r.left;
    mouseRef.current.y = ev.clientY - r.top;
    mouseRef.current.inside = true;
    if (dragRef.current) {
      const dx = mouseRef.current.x - dragRef.current.x;
      const barW = plotW.current / view.count;
      const ns = dragRef.current.start - dx / barW;
      setView((v) => ({ ...v, start: clampStart(data.length, v.count, ns) }));
    }
    redrawNextFrame();
  };

  const onMouseLeave = () => {
    mouseRef.current.inside = false;
    dragRef.current = null;
    redrawNextFrame();
  };

  const onMouseDown = (ev) => {
    const r = cvsRef.current.getBoundingClientRect();
    dragRef.current = { x: ev.clientX - r.left, start: view.start };
    cvsRef.current.style.cursor = 'grabbing';
  };

  const onMouseUp = () => {
    dragRef.current = null;
    if (cvsRef.current) cvsRef.current.style.cursor = 'crosshair';
  };

  return (
    <div ref={wrapRef} className="flex-1 relative min-w-0">
      <canvas
        ref={cvsRef}
        onMouseMove={onMouseMove}
        onMouseLeave={onMouseLeave}
        onMouseDown={onMouseDown}
        onMouseUp={onMouseUp}
        onDoubleClick={onReset}
        onContextMenu={(ev) => ev.preventDefault()}
        style={{ cursor: 'crosshair', display: 'block' }}
      />
    </div>
  );
}

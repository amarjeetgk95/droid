# TradingChart

A self-contained, TradingView-style candlestick chart built with plain React +
Canvas. **No indicators** (moving averages / volume panes removed) — clean
price action only, no charting library dependency.

## Files

```
src/components/TradingChart/
├── TradingChart.jsx     # top-level component (compose this)
├── ChartCanvas.jsx      # canvas rendering + zoom/pan/crosshair/touch
├── TopBar.jsx           # symbol, timeframe, chart type, live toggle
├── SideTools.jsx        # left drawing-tool rail (UI only, hook up as needed)
├── Legend.jsx           # OHLC legend + Δ vs previous close, updates on hover
├── StatusBar.jsx        # bottom clock + visible range stats
├── useCandleData.js     # data hook — swap this for your real data source
├── utils.js             # formatting/math helpers (pure functions)
├── constants.js         # colors, paddings, timeframe list
├── TradingChart.css     # the few non-Tailwind classes it needs
└── index.js             # barrel export
```

## Requirements

- React 18+ (function components + hooks only)
- Tailwind CSS is used for layout utility classes (`flex`, `absolute`, etc.).
  If your project doesn't have Tailwind, those classes will simply be ignored —
  either add Tailwind or replace them with your own layout CSS. The chart's
  own visuals (colors, buttons, tool icons, live dot) live in
  `TradingChart.css` and don't require Tailwind.

No other npm packages are required.

## Install into your project

1. Copy the whole `TradingChart` folder into your `src/components/` directory.
2. Import and use it:

```jsx
import TradingChart from './components/TradingChart';

function App() {
  return (
    <div style={{ height: '100vh' }}>
      <TradingChart symbol="BTCUSDT" />
    </div>
  );
}
```

The component fills its parent container (`h-full w-full`), so wrap it in an
element with an explicit height (`h-screen`, `h-[600px]`, flex-1 in a flex
column, etc).

## Props

| Prop               | Type   | Default              | Description                          |
|--------------------|--------|----------------------|---------------------------------------|
| `symbol`           | string | `'BTCUSDT'`          | Display label in header/legend/watermark |
| `exchangeLabel`    | string | `'Binance · Crypto'` | Subtitle under the symbol             |
| `defaultTimeframe` | number | `60`                 | Initial timeframe in minutes          |
| `className`        | string | `''`                 | Extra classes on the root container   |
| `style`            | object | `undefined`          | Inline styles on the root container   |

## Features

- Candlestick / line / area rendering on HiDPI canvas
- Hover: crosshair, axis price tag with Δ% vs last price, floating OHLC tooltip,
  hovered-bar column highlight
- Auto-scaled price axis with precision that adapts to the visible range
- Time axis with day separators when the view spans multiple days
- Last-price dashed line with colored axis chip, faint symbol watermark
- Wheel zoom (anchored at cursor), drag / single-touch pan, two-finger pinch zoom
- Keyboard: `+`/`−` zoom, `←`/`→` pan, `R` reset, double-click resets too
- Fit button (⤢), live feed toggle with pulsing dot, UTC clock + visible range
  stats in the status bar

## Connecting real market data

Replace `useCandleData` with your own hook (REST polling, WebSocket, etc.)
that returns an array of bars shaped like:

```js
{ t: 1716400000000, o: 63250.1, h: 63310.5, l: 63180.0, c: 63290.2, v: 812.4 }
```

`t` is a millisecond timestamp, `o/h/l/c` are price levels, `v` is volume.
Everything downstream (rendering, legend, status bar) only depends on that
shape, so you can swap the hook without touching any other file. For example:

```js
// useCandleData.js replacement sketch
export function useCandleData(tf, live) {
  const [data, setData] = useState([]);
  useEffect(() => {
    fetch(`/api/candles?interval=${tf}m`)
      .then((r) => r.json())
      .then(setData);
  }, [tf]);

  useEffect(() => {
    if (!live) return;
    const ws = new WebSocket(`wss://your-feed/${tf}`);
    ws.onmessage = (ev) => {
      const bar = JSON.parse(ev.data);
      setData((prev) => mergeBar(prev, bar));
    };
    return () => ws.close();
  }, [tf, live]);

  return data;
}
```

## Notes

- All interaction (zoom, pan, crosshair, touch) lives in `ChartCanvas.jsx`;
  wheel/touch are attached natively (non-passive) so the page doesn't scroll
  while zooming/panning the chart.
- `SideTools` renders drawing-tool buttons but doesn't implement drawing;
  wire `onSelect` if you want to add trend-lines/rectangles later.
- The chart is HiDPI-aware and resizes via `ResizeObserver`, so it works
  inside resizable panels/dashboards.

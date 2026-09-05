# How Signal is Generated - Complete Procedure in Simple Language

This document explains **step-by-step how a trading signal is created** in this project (Droid).
Language is kept very simple so anyone can understand it, even without deep coding knowledge.

> For developers: actual code file names are given in brackets like `backend/app/signals/scanner.py`
> so you can go and check the code directly.

---

## 1. What is a Signal in One Line?

A **Signal** = System says:

> "NIFTY looks like going UP, you can think about buying NIFTY CALL option. Entry around 100, Stop-loss 80, Target 130 and 160. Confidence 75%."

It is only for **research and paper-trading (virtual trading)**, not real money auto-trading.

A signal always contains:
- What to buy: NIFTY / BANKNIFTY / SENSEX, CALL (for UP) or PUT (for DOWN)
- Exact option contract: strike price, expiry, lot size e.g. `NSE:NIFTY26SEP...CE`
- Trigger price (when to become active), Stop-loss, Target 1, Target 2
- Confidence % (how strong system thinks it is)
- Reason (why it was created)
- Validity time (after some minutes it expires)

---

## 2. Full Journey in 30 Seconds

Think of signal generation like making juice in a factory:

```
1. START MACHINE (background worker starts)
       ↓
2. CHECK SHOP OPEN? (Is market open 9:15 to 15:30, Mon-Fri?)
       ↓
3. COLLECT FRUITS (Live price, candles, option data)
       ↓
4. CHECK QUALITY (Calculate indicators like RSI, MACD, ADX, VWAP)
       ↓
5. SEE BIG PICTURE (Check 1-min, 5-min, 15-min, 1-hour charts + Market mood)
       ↓
6. 9 CHEFS TASTE (9 different strategies try to find opportunity)
       ↓
7. 4 SECURITY CHECKS (Reject bad / risky / duplicate signals)
       ↓
8. AI GIVES MARKS (Combine all scores into final confidence %)
       ↓
9. TOKEN ISSUED (Signal is registered with ID)
       ↓
10. SAVE IN REGISTER (Save in Database + file)
       ↓
11. ANNOUNCE (Show on website, send Telegram message)
       ↓
12. WAIT AND WATCH (Wait for price to touch trigger, then track to Target or Stop-loss)
       ↓
13. CLOSE AND REPORT (Result saved, performance updated)
```

Now let us understand each step in detail.

---

## 3. Step 1 - System Start and Background Workers

**File:** `backend/app/main.py`, `backend/app/signals/worker.py`

When backend server starts:

1. It loads old saved signals from database (`executed_signals` table) and from backup file `signals_state.json`. So even if server restarts, old signals are not lost.
2. It starts live market connection (Fyers provider).
3. It starts a worker called `AutomatedSignalWorker` which runs non-stop in background like a watchman:
   - **Scalp scan:** every **10 seconds** - for very fast short trades.
   - **Intraday scan:** every **30 seconds** - for slightly bigger trades.
   - **Risk check loop:** every **3 seconds** - only watches already created signals to see if Target / Stop-loss hit.

No human clicks anything here. It is fully automatic during market hours.

**Simple meaning:** A robot wakes up every 10-30 seconds and asks "Is there any new opportunity?"

---

## 4. Step 2 - Check: Is Market Open?

**Files:** `backend/app/services/calendar_service.py`, `backend/app/signals/market_guard.py`

Before doing anything, system checks:

- Is today Saturday / Sunday? → Stop, no scan.
- Is today holiday? → Stop.
- Is time before 9:15 or after 15:30 IST? → Stop.
- Is it pre-open? → Stop.

This check happens at 5 places: scanner, risk check, paper trade, result tracking, and manual API. This is to make sure no signal is made with closed-market or wrong price.

**Simple meaning:** Shop closed = no juice. Only work when NSE is OPEN.

---

## 5. Step 3 - Collect Raw Data

**Files:** `backend/app/services/market_service.py`, `backend/app/fno/context.py`

For each item - NIFTY, BANKNIFTY, SENSEX - robot collects 3 things:

### A. Live Price (Quote)
Example: NIFTY = 25,120.5

System rejects price if:
- Price is 0 or negative
- Price is old (more than ~15 seconds old)
- Price comes from mock / fallback / synthetic source. Only real broker price allowed.

### B. Candles (Chart History)
Candles of 1-minute, 5-minute, 15-minute, 1-hour timeframes. Fetched parallelly within 8 seconds timeout.

Candle = Open, High, Low, Close, Volume for that time.

### C. F&O Data (Option Crowd Behaviour)
From `get_fno_context()`:
- PCR (Put-Call Ratio) - are more people buying PUT or CALL?
- Max Pain - where option sellers feel least pain
- ATM IV (volatility)
- Call Wall / Put Wall (big resistance / support)
- Futures basis and Open Interest

If option data fails, system uses safe default values but marks it as `DEGRADED` (low trust).

**Simple meaning:** Collect current price + past chart + what option crowd is doing.

---

## 6. Step 4 - Calculate Indicators (Technical Analysis)

**File:** `backend/app/technical_analysis/analyzer.py` + 9 files inside that folder

Just like doctor does blood test, system calculates health of market:

| Test | What it tells in simple words |
|------|-------------------------------|
| Trend + ADX + Supertrend | Is market going UP, DOWN, or SIDEWAYS? How strong is trend? |
| RSI, MACD | Is it over-bought (too costly) or over-sold (too cheap)? Is speed increasing? |
| ATR, Bollinger Bands | How much price jumps up-down? Is market calm or shaky? |
| Volume | Are many people trading or very few? |
| Candlestick patterns | Special shapes like Hammer, Doji, Engulfing - what buyers/sellers are thinking? |
| Chart patterns | Bigger shapes like Triangle, Head-Shoulder, Flag |
| Divergence | Price going up but power going down = warning |
| Support / Resistance | Floor (support) where price stops falling, Ceiling (resistance) where price stops rising |
| Price Action | Are highs getting higher? Or lower? Or market stuck? |

Output is:
- `bias = BULLISH (up) / BEARISH (down) / NEUTRAL`
- `score` for trend, momentum, volume, volatility, structure, and overall score.

**Simple meaning:** Convert raw candles into easy signals like "Trend is UP, power is good, volume is high".

---

## 7. Step 5 - See Bigger Picture: Multi-Timeframe + Market Mood + VWAP

**Files:** `backend/app/multi_timeframe/alignment.py`, `backend/app/services/regime_service.py`, `backend/app/signals/scanner.py`

One timeframe can lie. So system checks 1m, 5m, 15m, 1h, 4h, 1D together. This is called **MTF Alignment**.

Example:
- 1-min says BUY, but 1-hour says SELL strongly = conflict, system becomes careful.

Then system decides **Regime** = mood of market:
- `TREND_UP` - strong uptrend
- `TREND_DOWN` - strong downtrend
- `RANGE` - sideways, going left-right
- `HIGH_VOL` - too shaky, risky
- `COMPRESSION_SQUEEZE`, `VOLATILE_EXPANSION` etc. - special moods

Then system calculates **VWAP** = average price of day considering volume. VWAP is like fair price of the day.
- Price far above VWAP = costly
- Price far below VWAP = cheap
- Price near VWAP = fair

All this is packed into one box called `StrategyContext` which is given to strategies.

**Simple meaning:** Don't decide by looking at only 1 photo. Look at album + mood + fair price.

---

## 8. Step 6 - 9 Strategies Try to Find Opportunity

**Folder:** `backend/app/signals/strategies/`
**Base file:** `base.py` → `Strategy.detect()` returns `SignalCandidate`

There are 9 specialists (strategies). Each looks for different situation. Scalp desk (fast) and Intraday desk (slow) use different groups.

### Scalp Strategies (very fast, small profit, 90 to 480 seconds life):

1. **VWAP Scalp (`vwap_scalp.py`)** - Price went too far from fair price (0.3% away) and now returning back. Works only when market is NOT trending strongly.
2. **Micro Momentum (`micro_momentum.py`)** - Price was sleeping in tight range for 5 candles, then suddenly jumps with big volume + RSI > 60. Like spring release.
3. **EMA Ribbon Scalp (`ema_ribbon.py`)** - All moving averages lined up in one direction (trend), take quick ride.
4. **Gamma Spike (`gamma_spike.py`)** - Sudden option activity spike, works mostly 1:15 PM to 3:15 PM in volatile market.

### Intraday Strategies (bigger, 10 min to ~75 min life):

5. **Breakout (`breakout.py`)** - Price breaks ceiling (resistance) with 1.4x volume and strong buying pressure (68+). Example: NIFTY crosses 25,200 with force.
6. **Mean Reversion (`mean_reversion.py`)** - Price touches lower Bollinger Band + RSI below 28 (too cheap) → expect bounce up. Opposite for short. Works only in sideways market.
7. **Trend Pullback (`trend_pullback.py`)** - Market is in uptrend, price comes slightly down for rest, then goes up again. Like catching running bus when it slows a bit.
8. **Gamma Squeeze (`gamma_squeeze.py`)** - Option sellers trapped, PCR at extreme, sudden unwind → fast move.
9. **Opening Range Breakout ORB (`orb.py`)** - Note first 15 min high-low (9:15-9:30). If price breaks that range between 9:30-11:30 with volume, take trade.

Each strategy if successful creates a **Candidate** with:
- direction: `LONG_CALL` (buy CE, expects UP) or `LONG_PUT` (buy PE, expects DOWN)
- entry range, trigger price, stop-loss, target1, target2
- risk points, reward ratio
- which option contract: system auto-selects ATM strike using `contract_resolver.py` (e.g. NIFTY lot 75, strike step 50)
- TTL (how long valid)

**Simple meaning:** 9 different experts look at same market. Whoever sees his favourite pattern shouts "I found one!"

---

## 9. Step 7 - 4 Security Gates (Filters)

Most candidates get REJECTED here. Only best pass. Order is fixed:

### Gate 1: Scalp 6-Gate Check (for fast trades only)
**File:** `backend/app/signals/scalp_confirmation.py`

- Clock skewed? Data older than 120 sec? → Reject
- Same signal already given? (fingerprint check) → Reject
- Last signal was within 60 sec cooldown? → Reject
- Price already ran away >0.5R? (chasing) → Reject, too late
- Wrong market mood for this strategy? → Reject
- Spread too high (>2.5 points and >2.5%)? → Reject, costly
- Liquidity low (<250)? → Reject, difficult to exit

### Gate 2: Central Risk Check
**File:** `backend/app/signals/risk_engine.py`, rules in `config/risk_envelopes.json`

- Market closed? → Reject
- Stop-loss in wrong direction? → Reject
- Risk too big for allowed envelope? (e.g. NIFTY risk must be 14-32 points) → Reject
- Reward too small? (Reward:Risk < minimum, usually 1.2) → Reject
- Not enough capital for 1 lot? → Reject

If passes, it also decides:
- Correct stop-loss, target1, target2
- How many lots: `lots = min(10, allowed_risk / loss_per_lot)`
- Quantity, max loss in rupees, time-stop (max holding time: scalp 900 sec, intraday 4500 sec)

### Gate 3: Trigger Geometry Check
**File:** `backend/app/signals/trigger_gate.py`

Maths check:
- Trigger on wrong side? (Buy signal but trigger below price) → Reject
- Trigger too close to price (<0.05% or <2 ticks)? → Reject, will instantly trigger
- Stop-loss on wrong side? Target on wrong side? → Reject
- Risk too tiny (<0.03% of spot)? → Reject, just noise
- Entry zone too wide (>2R)? → Reject, unclear entry

### Gate 4: Duplicate Check
**File:** `backend/app/signals/scanner.py::_process_candidates()`

If same underlying + same strategy + same direction already ACTIVE and not expired → skip new one.

**Simple meaning:** 4 strict guards. Bad, risky, wrong-maths, or duplicate ideas are thrown in dustbin. Only clean ideas go ahead.

---

## 10. Step 8 - AI Scoring and Final Confidence

**Files:** `backend/app/signals/confluence.py`, `backend/app/services/ai_service.py`, `backend/app/ai/*`, `backend/app/ml/predictor.py`

System now combines all marks like school report card:

```
Final Score = 40% Technical + 20% Multi-timeframe + 20% F&O + 10% Regime + 10% AI
```

- Technical = from Step 4 indicators
- MTF = from Step 5 alignment
- F&O = option crowd support?
- Regime = market mood support?
- AI = quick AI bias (1500ms timeout) + historical similar cases (400ms) + ML model (XGBoost) prediction

If AI times out, remaining marks are re-adjusted so system never stops.

- If final score >= 70 → state = `ARMED` (strong)
- Else → state = `VALIDATED` (ok, but less strong)

Other AI helpers:
- `ScalpingAI` - special fast check for 1-min trades
- `SignalScorer` - gives confidence from 6 parts
- `MLPredictor` - tells bullish % / bearish % / neutral %
- `SignalFusion` - if different engines fight, decides final LONG / SHORT (LONG if >=62, SHORT if <=38)

**Simple meaning:** All teachers give marks, total % becomes confidence. 75% means strong, 55% means weak but still shown.

---

## 11. Step 9 - Signal Registration (Birth Certificate)

**File:** `backend/app/signals/fsm.py::SignalFSMManager.register()`

Once passed, signal gets official birth:

- `signal_id` = unique ID like `uuid`
- All details frozen: underlying, strategy, direction, timeframe, spot, entry, trigger, stop, target1/2, confidence, reason, option contract, lots, quantity, expiry time
- `created_at`, `expires_at = created + TTL`
- `risk_r = |trigger - stop-loss|` (1R = base unit)
- `breakeven_trigger = +0.8R` (if profit reaches 0.8R, stop-loss moves to cost)
- State = `DETECTED → ARMED / VALIDATED`
- State history list starts

States in life:
```
DETECTED → VALIDATED → ARMED → TRIGGERED → CONFIRMED → TARGET_1_HIT → TARGET_2_HIT / STOP_LOSS_HIT / TIME_STOP_HIT → CLOSED
                                                                                    ↘ EXPIRED / INVALIDATED
```

**Simple meaning:** Baby gets name, birth certificate, and enters school register.

---

## 12. Step 10 - Saving (So Data Never Lost)

**Files:** `backend/app/signals/signals_persistence.py`, `audit_ledger.py`, `fill_reconciler.py`

3 notebooks maintained:

1. **Main DB (Postgres table `executed_signals`)** - permanent record, upsert by signal_id.
2. **Local file `signals_state.json`** - backup `{signals, audit_trades, fills}`, saved atomically (write temp then rename) so power-cut safe.
3. **Audit Ledger** - money notebook: entry price, exit price, quantity, profit/loss in Rs, holding time, status ARMED/EXECUTED/WON/LOST, live MTM profit.
4. **Fill Reconciler** - option premium calculator using Black76 formula minus charges (STT, brokerage, GST etc. from `quant/costs.py`).

On server restart, system reads DB first, then file, cleans bad entries (test signals, ghost prices like NIFTY <22k) via `sanitize_persisted_signals()`.

**Simple meaning:** Write in 3 places so even if computer restarts, your notebook is safe.

---

## 13. Step 11 - Announcement: Website + Telegram + API

**Files:** `backend/app/institutional/telegram_notifications.py`, `backend/app/signals/sse.py`, `backend/app/api/signals.py`, `frontend/src/components/signals/*`

As soon as signal is registered:

1. **Telegram message `POSSIBLE_SETUP`** - "New setup found: NIFTY CALL, trigger 100, SL 80, TGT 130/160, confidence 75%"
2. **Website live update via SSE** - `GET /api/v1/signals/stream` sends `signal_created` event instantly, no refresh needed. Priority P0 (never dropped).
3. **API ready:**
   - `GET /active` - see all live signals
   - `GET /scanner?desk=SCALP/INTRADAY/ALL` - rescan on demand (10 sec cache)
   - `GET /performance` - win rate, profit factor
   - `GET /{id}/deep-dive` - full reason
   - `POST /generate` - human can manually create signal (with full validation)
   - `POST /{id}/execute-paper` - 1-click virtual buy
4. **Frontend cards:** `SignalCard.tsx`, `SignalScannerTable.tsx`, `SignalAuditTable.tsx`, `SignalDeepDiveModal.tsx`, `SignalPerformanceView.tsx` show it beautifully + sound alert + auto-refresh via `useSignalStream.ts`.

**Simple meaning:** Drum beating - everyone (website, mobile Telegram) told at same time.

---

## 14. Step 12 - Wait for Trigger and Track Live (Most Important Loop)

**Files:** `backend/app/signals/outcome_tracker.py`, `backend/app/signals/paper_engine.py`

This runs every 3 seconds in risk loop.

### Part A - Trigger:
- For CALL: if live price >= trigger → `TRIGGERED`
- For PUT: if live price <= trigger → `TRIGGERED`
- Then system tries virtual buy via `paper_engine.execute_signal()`:
  - Calculates position size, adds 0.05% spread cost, places order in `paper_service`.
  - If market closed or price invalid → FAIL, signal becomes `INVALIDATED`.
  - If success → state `CONFIRMED` + Telegram `SIGNAL_CONFIRMED` + website `signal_confirmed`.

### Part B - After Confirmation, every tick checks in this order:
1. Stop-loss hit? → Close all, status LOST, Telegram `STOP_HIT` + `SIGNAL_RESULT`.
2. Target 2 hit? → Close all, status WON.
3. Target 1 hit? → Book 50% profit (sell half lots), move stop-loss to cost (breakeven), Telegram `TARGET_HIT`, website `staged_exit`. Remaining half continues as runner for Target 2.
4. Time over? (`time_stop`) → Close, Telegram `TIME_STOP`.
5. Breakeven activated (+0.8R profit)? → Move SL to entry cost so trade becomes risk-free.

All profit = `(exit - entry) * quantity - charges`.

**Simple example:**
- You buy at 100, SL 80 (risk 20), T1 130 (profit 30), T2 160 (profit 60).
- Price goes 130 → sell half, profit locked, SL moved to 100.
- Then price goes 160 → sell rest, big win.
- If price goes 80 directly → full loss, close.

**Simple meaning:** Watchman watches every 3 sec. When price touches trigger, do virtual entry. Then guard till either profit target, loss limit, or time over.

---

## 15. Step 13 - Expiry and Cleanup

**File:** `backend/app/signals/fsm.py::sweep_expired()`

Every scan and every tick, cleaner runs:

- Scalp signals live only 90-240 sec trigger wait + 240-480 sec runner max.
- Intraday signals live 600 sec trigger wait + 4500 sec (~75 min) max.
- If time over before trigger → `EXPIRED`.
- If market closed or signal from yesterday → `EXPIRED` or `CLOSED (EOD_SQUARE_OFF)`.
- If runner after T1 stays >30 min → `RUNNER_TIME_STOP_HIT`.
- Keep only latest 200 signals + 1000 audits, delete old to save memory.
- Clean test signals (`SIG-TEST-*`) and wrong prices.

Worker also does final sweep after market close.

**Simple meaning:** Milk has expiry date. Old signals auto-removed so screen stays clean.

---

## 16. Step 14 - Manual Signal (Human Creates)

**API:** `POST /api/v1/signals/generate`, `POST /auto-detect`, `POST /preview`

Human can also create signal from UI form `GenerateSignalForm.tsx`:

System validates:
- Underlying must be NIFTY/BANKNIFTY/SENSEX only
- Timeframe valid, direction LONG_CALL/LONG_PUT
- Price in sensible range (e.g. NIFTY 22k-35k, BANKNIFTY 54k-75k)
- Price drift <5% from live, trigger geometry passes
- Then same steps: FSM register → save → Telegram → SSE → tracking.

`auto-detect` = you give instrument, system scans that one instantly.

**Simple meaning:** Auto robot + manual button both use same safety pipeline.

---

## 17. Separate Path 1: Master AI Pipeline (Second Engine)

**File:** `backend/app/services/master_pipeline.py::MasterPipeline.evaluate()`

This is a second, more AI-heavy route (used for research):

```
VALID_DATA → TECH_FEATURES → DIRECTION → TRIGGER_CHECK → SAVE_MARKET_STATE → AI_ROUTER → VALIDATE_AI → STALENESS_CHECK → QUANT_CONFIRM → PRICING → RISK_REWARD → POSITION_SIZE → CREATE_SIGNAL
```

Outcome can be `SIGNAL_CREATED` or `NO_TRADE / WAIT / RISK_REJECTED / STALE / INVALID_*`.

**Simple meaning:** Same destination, but via AI-first road with extra checks.

---

## 18. Separate Path 2: Crypto Signals (Different Market)

**Files:** `backend/app/services/crypto_signal_engine.py`, `backend/app/api/crypto.py`

Crypto runs 24x7 separately, not dependent on NSE timing:

- `DEPTH_IMBALANCE_FLOW` - order book heavily one-sided (>=12%)
- `FUNDING_SQUEEZE` - funding rate too negative/positive (crowd over-shorted/over-long)
- `BASIS_DIVERGENCE` - futures price far from spot (>=0.06%)
- `ETH_BTC_MOMENTUM` - ETH/BTC ratio momentum

Gives entry/SL/T1/T2 with 1.8-3.4R reward, shown in `CryptoSignalsCard.tsx`.

**Simple meaning:** Crypto is separate shop, open 24 hours, with its own 4 experts.

---

## 19. One Full Real Example

Let us join all steps:

1. 10:05:00 AM, NIFTY at 25,100. Market OPEN.
2. Scanner collects: quote 25,100, 1m/5m/15m candles, PCR 1.2 (bullish), ATM IV 13.
3. Indicators: RSI 62, MACD up, ADX 27 BULLISH, volume 1.6x, price above VWAP, support 25,050, resistance 25,120.
4. MTF: 1m BUY, 5m BUY, 15m BUY, 1h BUY → alignment high, regime TREND_UP.
5. BreakoutStrategy sees: Close 25,125 >= Resistance 25,120 + volume 1.6x + pressure 72 + MTF not opposite → creates candidate LONG_CALL, trigger 25,130, SL 25,110 (risk 20), T1 25,160, T2 25,190, option NIFTY 25,150 CE.
6. Gates: not duplicate, spread ok, risk 20 fits envelope 14-32, RR 1.5 ok, trigger geometry ok → PASS.
7. Confluence: tech 80*0.4=32 + mtf 85*0.2=17 + fno 70*0.2=14 + regime 75*0.1=7.5 + AI 72*0.1=7.2 = 77.7% → ARMED.
8. Registered: ID `abc-123`, lots 2, qty 150, max loss Rs 3000, TTL 600 sec.
9. Saved in DB + file + audit. Telegram POSSIBLE_SETUP sent. Website card appears with sound.
10. 10:05:21, price 25,132 >= trigger → paper buy at ~12.5 premium → CONFIRMED, Telegram SIGNAL_CONFIRMED.
11. 10:12, price hits T1 → sell 75 qty, profit booked, SL moved to cost, Telegram TARGET_HIT.
12. 10:28, price hits T2 → sell remaining 75, total profit e.g. Rs 4500 - charges = Rs 4300 net, status WON, Telegram SIGNAL_RESULT.
13. Performance page win-rate updated. After TTL/market close, signal CLOSED and archived.

If price instead fell to SL, same flow but status LOST.

---

## 20. Files Map - Where to Look What

| If you want to understand... | Open this file |
|------------------------------|----------------|
| When scanning happens | `backend/app/signals/worker.py` |
| What data collected | `backend/app/services/market_service.py`, `backend/app/fno/context.py` |
| Indicators calculation | `backend/app/technical_analysis/analyzer.py` |
| Big picture / regime | `backend/app/multi_timeframe/alignment.py`, `backend/app/services/regime_service.py` |
| Strategies logic | `backend/app/signals/strategies/*.py` (9 files) |
| Scalp safety | `backend/app/signals/scalp_confirmation.py` |
| Risk + lots sizing | `backend/app/signals/risk_engine.py`, `config/risk_envelopes.json` |
| Trigger maths check | `backend/app/signals/trigger_gate.py` |
| AI + confidence | `backend/app/signals/confluence.py` |
| Signal birth / life states | `backend/app/signals/fsm.py` |
| Saving / backup | `backend/app/signals/signals_persistence.py` |
| Profit notebook | `backend/app/signals/audit_ledger.py`, `fill_reconciler.py` |
| Live tracking | `backend/app/signals/outcome_tracker.py`, `paper_engine.py` |
| Telegram + website live | `backend/app/institutional/telegram_notifications.py`, `backend/app/signals/sse.py` |
| APIs | `backend/app/api/signals.py` |
| Website UI | `frontend/src/components/signals/`, `frontend/src/hooks/useSignalStream.ts` |

---

## 21. Summary for Quick Revision

1. Worker wakes every 10s/30s.
2. Market open? Else stop.
3. Get live price + candles + option data.
4. Calculate indicators.
5. Check all timeframes + mood + VWAP.
6. 9 strategies search pattern.
7. 4 guards reject bad ones.
8. AI gives final %.
9. Register with ID + expiry.
10. Save in DB + file.
11. Announce on website + Telegram.
12. Wait for trigger → virtual buy.
13. Track to Target / Stop / Time.
14. Save result, update performance, auto-clean old.

That's the complete procedure.


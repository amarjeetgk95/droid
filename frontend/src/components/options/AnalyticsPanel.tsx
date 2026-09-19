'use client';

import { Card } from '@/components/ui/desk';
import { fmtExpiry, getObj, pickNum, pickStr } from '@/lib/signalsNormalize';
import { safeInt, safeNum, safeStr } from '@/lib/utils';
import type {
  InstitutionalFlowResponse,
  KeyLevelsModel,
  MarketRegimeOverview,
  MaxPainResult,
  OptionsAnalytics,
  TechnicalIndicators,
  VixRegimeInfo,
} from '@/lib/types';
import {
  buildupTone,
  pcrNote,
  pcrTone,
  regimeBadge,
  sentimentTone,
  topFlowsByVolume,
  vixBadge,
} from '@/lib/optionsDesk';

function analyticsRecord(analytics: OptionsAnalytics | null): Record<string, unknown> | null {
  return getObj(analytics);
}

/** Slim CommandView legs (`{pcr, max_pain, ...}`) share keys with the REST shape. */
function numOf(record: Record<string, unknown> | null, ...keys: string[]): number | null {
  if (!record) return null;
  return pickNum(record, ...keys);
}

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div className="sg-kv">
      <span className="l">{label}</span>
      <span className="v">{value}</span>
    </div>
  );
}

function toneClass(tone: string): string {
  if (tone === 'bull') return 'bull';
  if (tone === 'bear') return 'bear';
  if (tone === 'warn') return 'warn';
  if (tone === 'info') return 'info';
  return 'neut';
}

export function AnalyticsPanel({
  analytics,
  analyticsSource,
  maxPain,
  flow,
  regime,
  regimeSource,
  pivots,
  indicators,
  vix,
}: {
  analytics: OptionsAnalytics | null;
  analyticsSource: 'stream' | 'rest';
  maxPain: MaxPainResult | null;
  flow: InstitutionalFlowResponse | null;
  regime: MarketRegimeOverview | null;
  regimeSource: 'stream' | 'rest';
  pivots: KeyLevelsModel | null;
  indicators: TechnicalIndicators | null;
  vix: VixRegimeInfo | null;
}) {
  const a = analyticsRecord(analytics);
  const pcrOi = numOf(a, 'pcr_oi', 'pcr');
  const pcrVol = numOf(a, 'pcr_volume', 'pcr_vol');
  const maxPainStrike = numOf(a, 'max_pain_strike', 'max_pain') ?? maxPain?.max_pain_strike ?? null;
  const atmStrike = numOf(a, 'atm_strike');
  const atmIv = numOf(a, 'atm_iv');
  const spot = numOf(a, 'spot_price', 'spot');
  const futures = numOf(a, 'futures_price', 'futures');
  const expiry = a ? pickStr(a, 'expiry') : null;

  const sentiment = flow?.institutional_sentiment ?? null;
  const topFlows = topFlowsByVolume(flow?.strike_flows, 8);
  const regimeMeta = regimeBadge(regime?.regime_state);
  const vixMeta = vixBadge(vix?.regime_category);

  return (
    <div className="flex flex-col gap-3">
      <div className="pnl-strip" aria-label="Positioning summary">
        <span className="ps">
          <span className="ps-l">PCR (OI)</span>
          <span className="ps-v num">{pcrOi !== null ? safeNum(pcrOi) : '—'}</span>
        </span>
        <span className="ps">
          <span className="ps-l">Max pain</span>
          <span className="ps-v num">{maxPainStrike !== null ? safeNum(maxPainStrike, '—', 0) : '—'}</span>
        </span>
        <span className="ps">
          <span className="ps-l">ATM IV</span>
          <span className="ps-v num">{atmIv !== null ? `${safeNum(atmIv)}%` : '—'}</span>
        </span>
        <span className="ps">
          <span className="ps-l">Flow bias</span>
          <span className="ps-v">{sentiment ? sentiment.replace(/_/g, ' ') : '—'}</span>
        </span>
      </div>

      <Card
        title="Regime"
        meta={`${regimeSource === 'stream' ? 'CommandView' : 'REST'} · ${regime?.symbol ?? '—'}`}
      >
        {!regime ? (
          <p className="sg-empty">Regime classification unavailable.</p>
        ) : (
          <div className="flex flex-col gap-3">
            <div>
              <span className={`badge ${regimeMeta.cls}`}>{regimeMeta.label}</span>
              <p className="sg-note">{safeStr(regime.summary_headline, '')}</p>
              <p className="sg-note">{safeStr(regime.institutional_rationale, '')}</p>
            </div>
            <div className="sg-kvlist">
              <KV label="Spot" value={safeNum(regime.spot_price)} />
              <KV
                label="Confidence"
                value={typeof regime.confidence_score === 'number' ? `${safeNum(regime.confidence_score, '—', 0)}%` : '—'}
              />
              <KV label="Support" value={safeNum(regime.key_levels?.nearest_support)} />
              <KV label="Resistance" value={safeNum(regime.key_levels?.nearest_resistance)} />
            </div>
          </div>
        )}
      </Card>

      <Card
        title="Options positioning"
        meta={`${analyticsSource === 'stream' ? 'CommandView' : 'REST'}${expiry ? ` · ${fmtExpiry(expiry)}` : ''}`}
      >
        {!a ? (
          <p className="sg-empty">Options analytics unavailable for this expiry.</p>
        ) : (
          <div className="flex flex-col gap-3">
            <div>
              <span className={`sg-tag ${toneClass(pcrTone(pcrOi))}`}>
                PCR {pcrOi !== null ? safeNum(pcrOi) : '—'} · {pcrNote(pcrOi)}
              </span>
            </div>
            <div className="sg-kvlist">
              <KV label="Spot" value={safeNum(spot)} />
              <KV label="Futures" value={safeNum(futures)} />
              <KV label="ATM strike" value={atmStrike !== null ? safeNum(atmStrike, '—', 0) : '—'} />
              <KV label="ATM IV" value={atmIv !== null ? `${safeNum(atmIv)}%` : '—'} />
              <KV label="PCR (OI)" value={pcrOi !== null ? safeNum(pcrOi) : '—'} />
              <KV label="PCR (vol)" value={pcrVol !== null ? safeNum(pcrVol) : '—'} />
              <KV label="Max pain" value={maxPainStrike !== null ? safeNum(maxPainStrike, '—', 0) : '—'} />
              <KV label="IV skew" value={safeNum(numOf(a, 'iv_skew'))} />
              <KV label="Total call OI" value={safeInt(numOf(a, 'total_call_oi'))} />
              <KV label="Total put OI" value={safeInt(numOf(a, 'total_put_oi'))} />
              <KV label="Total call vol" value={safeInt(numOf(a, 'total_call_volume'))} />
              <KV label="Total put vol" value={safeInt(numOf(a, 'total_put_volume'))} />
            </div>
            {maxPain ? (
              <p className="sg-note">
                Max-pain curve peaks at {safeNum(maxPain.max_pain_strike, '—', 0)} with
                writer loss {safeNum(maxPain.total_loss_at_max_pain, '—', 0)} at the pin.
              </p>
            ) : null}
          </div>
        )}
      </Card>

      <Card title="Institutional flow" meta={flow ? fmtExpiry(flow.expiry) : undefined}>
        {!flow ? (
          <p className="sg-empty">Institutional flow unavailable for this expiry.</p>
        ) : (
          <div className="flex flex-col gap-3">
            <div>
              <span className={`sg-tag ${toneClass(sentimentTone(sentiment))}`}>
                {sentiment ? sentiment.replace(/_/g, ' ') : 'NEUTRAL'} · score{' '}
                {safeNum(flow.institutional_score, '—', 1)}
              </span>
            </div>
            <div className="sg-kvlist">
              <KV label="Call wall" value={safeNum(flow.call_wall_strike, '—', 0)} />
              <KV label="Put floor" value={safeNum(flow.put_floor_strike, '—', 0)} />
              <KV label="Max pain" value={safeNum(flow.max_pain_strike, '—', 0)} />
            </div>
            {topFlows.length === 0 ? (
              <p className="sg-empty">No strike flows published for this expiry.</p>
            ) : (
              <div className="tbl-scroll">
                <table className="sg-table">
                  <thead>
                    <tr>
                      <th>Strike</th>
                      <th>Call buildup</th>
                      <th>Put buildup</th>
                      <th>Net flow</th>
                      <th className="r">Call vol</th>
                      <th className="r">Put vol</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topFlows.map((row) => (
                      <tr key={row.strike} data-active={row.is_atm}>
                        <td>
                          <span className="sg-sym num">{safeNum(row.strike, '—', 0)}</span>
                          <div className="sg-rownote">
                            OI Δ C {safeInt(row.call_oi_change)} / P {safeInt(row.put_oi_change)}
                          </div>
                        </td>
                        <td>
                          <span className={`sg-tag ${toneClass(buildupTone(row.call_buildup))}`}>
                            {row.call_buildup.replace(/_/g, ' ')}
                          </span>
                        </td>
                        <td>
                          <span className={`sg-tag ${toneClass(buildupTone(row.put_buildup))}`}>
                            {row.put_buildup.replace(/_/g, ' ')}
                          </span>
                        </td>
                        <td>
                          {row.net_flow === 'BULLISH' || row.net_flow === 'BEARISH' ? (
                            <span className={`sg-dir ${row.net_flow === 'BULLISH' ? 'long' : 'short'}`}>
                              {row.net_flow}
                            </span>
                          ) : (
                            <span className="sg-tag neut">{row.net_flow}</span>
                          )}
                        </td>
                        <td className="r num">{safeInt(row.call_volume)}</td>
                        <td className="r num">{safeInt(row.put_volume)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </Card>

      <Card title="Key levels" meta={regime?.symbol ?? flow?.symbol ?? undefined}>
        {!pivots ? (
          <p className="sg-empty">Pivot levels unavailable.</p>
        ) : (
          <div className="sg-kvlist">
            <KV label="Classic P / R1 / S1" value={`${safeNum(pivots.classic_pivots?.pivot)} / ${safeNum(pivots.classic_pivots?.r1)} / ${safeNum(pivots.classic_pivots?.s1)}`} />
            <KV label="Classic R2 / S2" value={`${safeNum(pivots.classic_pivots?.r2)} / ${safeNum(pivots.classic_pivots?.s2)}`} />
            <KV label="Fib P / R1 / S1" value={`${safeNum(pivots.fibonacci_pivots?.pivot)} / ${safeNum(pivots.fibonacci_pivots?.r1)} / ${safeNum(pivots.fibonacci_pivots?.s1)}`} />
            <KV label="Camarilla R3 / S3" value={`${safeNum(pivots.camarilla_pivots?.r3)} / ${safeNum(pivots.camarilla_pivots?.s3)}`} />
            <KV label="POC / VAH / VAL" value={`${safeNum(pivots.poc)} / ${safeNum(pivots.vah)} / ${safeNum(pivots.val)}`} />
            <KV label="Nearest support" value={`${safeNum(pivots.nearest_support)} (${safeNum(pivots.distance_to_support_pts)} pts)`} />
            <KV label="Nearest resistance" value={`${safeNum(pivots.nearest_resistance)} (${safeNum(pivots.distance_to_resistance_pts)} pts)`} />
          </div>
        )}
      </Card>

      <Card title="Indicators">
        {!indicators ? (
          <p className="sg-empty">Technical indicators unavailable.</p>
        ) : (
          <div className="sg-kvlist">
            <KV label="RSI 14" value={safeNum(indicators.rsi_14)} />
            <KV label="ADX 14" value={safeNum(indicators.adx_14)} />
            <KV label="+DI / −DI" value={`${safeNum(indicators.plus_di)} / ${safeNum(indicators.minus_di)}`} />
            <KV label="ATR 14" value={safeNum(indicators.atr_14)} />
            <KV label="Supertrend" value={`${safeNum(indicators.supertrend_value)} · ${indicators.supertrend_direction}`} />
            <KV label="Bollinger U / M / L" value={`${safeNum(indicators.bollinger_upper)} / ${safeNum(indicators.bollinger_middle)} / ${safeNum(indicators.bollinger_lower)}`} />
            <KV label="%B / bandwidth" value={`${safeNum(indicators.bollinger_pct_b)} / ${safeNum(indicators.bollinger_bandwidth)}`} />
            <KV label="EMA 20 / 50" value={`${safeNum(indicators.ema_20)} / ${safeNum(indicators.ema_50)}`} />
            <KV label="SMA 200" value={safeNum(indicators.sma_200)} />
          </div>
        )}
      </Card>

      <Card title="India VIX" meta={vix ? `${safeNum(vix.historical_percentile, '—', 0)}th pct` : undefined}>
        {!vix ? (
          <p className="sg-empty">VIX regime unavailable.</p>
        ) : (
          <div className="flex flex-col gap-3">
            <div>
              <span className={`badge ${vixMeta.cls}`}>{vixMeta.label}</span>{' '}
              <span className="card-meta num">
                {safeNum(vix.vix_value)} ({safeNum(vix.change_percent)}%)
              </span>
            </div>
            <p className="sg-note">{safeStr(vix.interpretation, '')}</p>
            <div className="sg-kvlist">
              <KV label="Suggested framework" value={safeStr(vix.recommended_option_strategy, '—')} />
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

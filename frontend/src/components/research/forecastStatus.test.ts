import { describe, expect, it } from 'vitest';
import {
  ABSTAIN_VERDICT,
  UNSETTLEABLE_NOTE,
  asStringList,
  calibrationLabel,
  getDataQualityLabel,
  getExpectedRange,
  getForecastStatusLabel,
  getSettlementLabel,
  isAbstainForecast,
  isCalibratedForecast,
  isDegradedForecast,
  maxProbability,
  normalizeForecastStatus,
  probabilityBars,
  shortForecastId,
} from './forecastStatus';

describe('forecast v2 status helpers', () => {
  it('v1 payloads without new keys default to RESEARCH (backward compatible)', () => {
    expect(getForecastStatusLabel({})).toBe('RESEARCH');
    expect(getForecastStatusLabel(null)).toBe('RESEARCH');
    expect(getForecastStatusLabel(undefined)).toBe('RESEARCH');
    expect(isDegradedForecast({})).toBe(false);
    expect(isAbstainForecast({})).toBe(false);
    expect(getSettlementLabel({})).toBeNull();
    expect(getDataQualityLabel({})).toBeNull();
    expect(shortForecastId(undefined)).toBeNull();
    expect(asStringList(undefined)).toEqual([]);
  });

  it('normalizes every known status and falls back on unknown', () => {
    expect(normalizeForecastStatus('RESEARCH')).toBe('RESEARCH');
    expect(normalizeForecastStatus('MVIG')).toBe('MVIG');
    expect(normalizeForecastStatus('DEGRADED')).toBe('DEGRADED');
    expect(normalizeForecastStatus('ABSTAIN')).toBe('ABSTAIN');
    expect(normalizeForecastStatus('degraded')).toBe('DEGRADED');
    expect(normalizeForecastStatus('whatever')).toBe('RESEARCH');
    expect(normalizeForecastStatus(null)).toBe('RESEARCH');
    expect(getForecastStatusLabel({ status: 'ABSTAIN' })).toBe('ABSTAIN');
    expect(isDegradedForecast({ status: 'DEGRADED' })).toBe(true);
    expect(isAbstainForecast({ status: 'ABSTAIN' })).toBe(true);
  });

  it('labels data quality and settlement chips', () => {
    expect(getDataQualityLabel({ data_quality: 'healthy' })).toBe('HEALTHY');
    expect(getDataQualityLabel({ data_quality: 'DEGRADED' })).toBe('DEGRADED');
    expect(getDataQualityLabel({ data_quality: 'HEURISTIC' })).toBe('HEURISTIC');
    expect(getDataQualityLabel({ data_quality: 'UNSETTLEABLE' })).toBe('UNSETTLEABLE');
    expect(getDataQualityLabel({ data_quality: '' })).toBeNull();
    expect(getSettlementLabel({ settleable: true })).toBe('YES');
    expect(getSettlementLabel({ settleable: false })).toBe('NO');
    expect(getSettlementLabel({ settleable: null })).toBeNull();
    expect(getSettlementLabel({})).toBeNull();
  });

  it('shortens prediction and snapshot ids', () => {
    expect(shortForecastId('forecast_1h_abc123def456')).toBe('abc123def456');
    expect(shortForecastId('forecast_1h_abc123def456extra')).toBe('abc123def456');
    expect(shortForecastId('snap_0011223344556677')).toBe('snap_0011223');
    expect(shortForecastId('')).toBeNull();
    expect(shortForecastId(null)).toBeNull();
  });

  it('keeps limitations list clean', () => {
    expect(asStringList(['a', ' b ', '', null, 42])).toEqual(['a', 'b']);
    expect(asStringList('not-an-array')).toEqual([]);
  });

  it('uses the exact honesty copy', () => {
    expect(UNSETTLEABLE_NOTE).toBe('Late-session — excluded from accuracy');
    expect(ABSTAIN_VERDICT).toBe('ABSTAIN — INSUFFICIENT EVIDENCE');
  });
});

describe('forecast v2 prob UI helpers (P3-4)', () => {
  it('probabilityBars hides v1 payloads and shows BULL/NEUT/BEAR% for v2', () => {
    expect(probabilityBars({})).toBeNull();
    expect(probabilityBars(null)).toBeNull();
    expect(probabilityBars({ probabilities: null })).toBeNull();
    expect(
      probabilityBars({ probabilities: { bullish: 0.9, neutral: 0.9, bearish: 0.9 } }),
    ).toBeNull();
    const bars = probabilityBars({ probabilities: { bullish: 0.6, neutral: 0.25, bearish: 0.15 } });
    expect(bars).not.toBeNull();
    expect(bars!.map((b) => b.label)).toEqual(['BULL', 'NEUT', 'BEAR']);
    expect(bars!.map((b) => b.pct)).toEqual([60, 25, 15]);
    expect(maxProbability({ probabilities: { bullish: 0.6, neutral: 0.25, bearish: 0.15 } })).toBeCloseTo(
      0.6,
      6,
    );
  });

  it('maxProbability falls back to confidence for v1', () => {
    expect(maxProbability({})).toBeNull();
    expect(maxProbability({ confidence: 0.42 })).toBeCloseTo(0.42, 6);
    expect(maxProbability({ confidence: 2 })).toBeNull();
  });

  it('calibrationLabel shows LIVE ECE when calibrated else UNCALIBRATED', () => {
    expect(calibrationLabel({})).toBe('UNCALIBRATED');
    expect(calibrationLabel({ calibrated: false })).toBe('UNCALIBRATED');
    expect(calibrationLabel({ calibrated: true, calibrator_version: 'none-v0' })).toBe('LIVE');
    expect(
      calibrationLabel({
        calibrated: true,
        calibrator_version: 'cal-v1',
        calibration: { ece: 0.045, n: 200 },
      }),
    ).toBe('LIVE ECE 0.04 n=200');
    expect(
      calibrationLabel({
        calibrated: true,
        explain: { calibration: { ece: 0.08, n: 120 } },
      }),
    ).toBe('LIVE ECE 0.08 n=120');
    expect(isCalibratedForecast({ calibrated: true })).toBe(true);
    expect(isCalibratedForecast({})).toBe(false);
  });

  it('getExpectedRange returns lower/mid/upper only when finite', () => {
    expect(getExpectedRange({})).toBeNull();
    expect(
      getExpectedRange({ expected_range: { lower: 24900, mid: 25000, upper: 25100 } }),
    ).toEqual({ lower: 24900, mid: 25000, upper: 25100 });
    expect(getExpectedRange({ expected_range: { lower: null, mid: 1, upper: 2 } })).toBeNull();
  });
});

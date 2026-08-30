import pytest
from app.instruments.resolver import resolve_instrument, search_instruments, normalize_query
from app.instruments.registry import get_by_symbol_exact
from app.technical_analysis.analyzer import analyze_timeframe
from app.prediction.features import build_features, feature_vector_for_model
from app.prediction.predictor import forecast_for_timeframe
from app.multi_timeframe.alignment import compute_alignment
import random
from datetime import datetime, timezone

def _candles(price=25000, n=50, seed=0):
    random.seed(seed)
    out=[]
    p=price
    for i in range(n):
        o=p; c=p+random.uniform(-50,50); h=max(o,c)+20; l=min(o,c)-20
        out.append({"open":o,"high":h,"low":l,"close":c,"volume":random.randint(100000,500000),"timestamp":datetime.now(timezone.utc).isoformat()})
        p=c
    return out

def test_resolve_alias():
    assert resolve_instrument("banknifty").symbol=="BANKNIFTY"
    assert resolve_instrument("  BANKNIFTY ").symbol=="BANKNIFTY"
    assert resolve_instrument("sensex").symbol=="SENSEX"
    assert resolve_instrument("bitcoin").symbol=="BTCUSD"
    assert resolve_instrument("nifty 50").symbol=="NIFTY"
    assert resolve_instrument("abc") is None

def test_search_case_insensitive_whitespace():
    assert search_instruments("BANKNIFTY")[0].symbol=="BANKNIFTY"
    assert search_instruments("banknifty")[0].symbol=="BANKNIFTY"
    assert search_instruments("  banknifty  ")[0].symbol=="BANKNIFTY"
    assert len(search_instruments("btc"))>=2
    assert len(search_instruments("xyz"))==0
    assert len(search_instruments("", limit=3))==3

def test_registry_timeframe():
    cfg=get_by_symbol_exact("BANKNIFTY")
    assert "1m" in cfg.supported_timeframes
    assert cfg.fno_available is True
    cfg2=get_by_symbol_exact("BTCUSD")
    assert cfg2.fno_available is False

def test_price_structure():
    c=_candles()
    ta=analyze_timeframe(c, "BANKNIFTY","15m")
    assert ta["bias"] in ("BULLISH","BEARISH","NEUTRAL")
    assert 0<=ta["score"]<=100
    assert "support" in ta["support_resistance"]

def test_volume_unavailable():
    c=[{"open":100,"high":101,"low":99,"close":100.5,"volume":0,"timestamp":datetime.now(timezone.utc).isoformat()}]*30
    ta=analyze_timeframe(c, "BTCUSD","15m")
    assert ta["volume"]["available"] is False

def test_forecast_probability_validity():
    c=_candles()
    ta=analyze_timeframe(c, "BTCUSD","15m")
    feat=build_features(c, ta, {"available":False}, {"asset_class":"CRYPTO","exchange":"BINANCE","instrument_type":"SPOT","currency":"USD"}, datetime.now(timezone.utc))
    fc=forecast_for_timeframe(feat, ta, "15m","BTCUSD","CRYPTO")
    assert abs(fc["direction"]["up"]+fc["direction"]["sideways"]+fc["direction"]["down"]-1) < 0.01
    assert fc["confidence"] in ("HIGH","MODERATE","LOW")
    assert "expected_range" in fc

def test_multi_timeframe_not_average():
    analyses={'1m':{'bias':'BULLISH','score':74},'5m':{'bias':'BULLISH','score':81},'15m':{'bias':'BULLISH','score':76},'1h':{'bias':'NEUTRAL','score':58}}
    forecasts={'1m':{'confidence_score':70,'direction':{'up':0.6,'sideways':0.2,'down':0.2},'expected_range':{'low':0,'high':0},'expected_move_percent':0,'horizon_minutes':10,'confidence':'MODERATE'},'5m':{'confidence_score':75,'direction':{'up':0.65,'sideways':0.2,'down':0.15},'expected_range':{'low':0,'high':0},'expected_move_percent':0,'horizon_minutes':20,'confidence':'MODERATE'},'15m':{'confidence_score':70,'direction':{'up':0.65,'sideways':0.2,'down':0.15},'expected_range':{'low':0,'high':0},'expected_move_percent':0,'horizon_minutes':60,'confidence':'MODERATE'},'1h':{'confidence_score':50,'direction':{'up':0.34,'sideways':0.33,'down':0.33},'expected_range':{'low':0,'high':0},'expected_move_percent':0,'horizon_minutes':120,'confidence':'LOW'}}
    align=compute_alignment(analyses)
    # weighted alignment should be 75, not simple average of scores (72.25)
    assert align['overall_bias']=='BULLISH'
    assert align['alignment_score']==75.0

def test_no_future_leakage():
    # build_features should not use future candle; returns dict with price from last candle
    c=_candles(price=30000)
    ta=analyze_timeframe(c, "NIFTY","5m")
    feat=build_features(c, ta, {"available":False}, {"asset_class":"INDEX","exchange":"NSE","instrument_type":"INDEX","currency":"INR"}, datetime.now(timezone.utc))
    assert feat["price"]==c[-1]["close"]

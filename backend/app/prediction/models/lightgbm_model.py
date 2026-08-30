import math
import random

class LightGBMModel:
    """Heuristic LightGBM-like model. Tries to load real artifact, else heuristic."""
    def __init__(self):
        self.trained=False
        self.model=None
        self.version="lightgbm-v1-heuristic"

    def predict_proba(self, features: list[float]) -> list[float]:
        # features: 22-dim vector as defined in features.py
        # heuristic: weighted ensemble of tree-like splits
        # use same logic as existing ml/predictor heuristic but simplified for chart forecast
        try:
            import json
            from pathlib import Path
            META = Path("backend/app/ml/meta.json")
            if META.exists():
                # try real ensemble
                from app.ml.trainer import ensemble_predict_proba
                # map our 22 features to 10-feature ensemble by slicing first 10 expected
                # need to map: our features include more; approximate
                vec10 = features[:10]
                # pad if needed
                while len(vec10)<10:
                    vec10.append(0)
                res = ensemble_predict_proba(vec10)
                if res:
                    bear, neut, bull = res
                    return [bull/100, neut/100, bear/100]  # up, sideways, down
        except Exception:
            pass
        # heuristic decision tree splits
        rsi_norm = features[0] if len(features)>0 else 0
        adx = features[1] if len(features)>1 else 0.3
        dist_ema20 = features[8] if len(features)>8 else 0
        dist_vwap = features[7] if len(features)>7 else 0
        pcr_dev = features[15] if len(features)>15 else 0
        basis = features[14] if len(features)>14 else 0
        # score -1..1
        score = 0.25* rsi_norm + 0.15* math.tanh(dist_ema20) + 0.15* math.tanh(dist_vwap) + 0.1* pcr_dev*0.5 + 0.1* math.tanh(basis*5) + 0.1* (adx-0.3)
        # leaf logic: if rsi high and price above ema -> bullish
        if score>0:
            up_logit=1.0 + score*2.5*(0.5+0.5*adx)
            down_logit=1.0 - score*1.5
            side_logit=1.0+(1-adx)*1.2
        else:
            up_logit=1.0+score*1.5
            down_logit=1.0 - score*2.5*(0.5+0.5*adx)
            side_logit=1.0+(1-adx)*1.2
        exp_up=math.exp(max(-5,min(5,up_logit)))
        exp_down=math.exp(max(-5,min(5,down_logit)))
        exp_side=math.exp(max(-5,min(5,side_logit)))
        total=exp_up+exp_down+exp_side
        return [exp_up/total, exp_side/total, exp_down/total]

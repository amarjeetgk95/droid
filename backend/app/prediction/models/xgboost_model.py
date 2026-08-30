import math

class XGBoostModel:
    def __init__(self):
        self.version="xgboost-v1-heuristic"
    def predict_proba(self, features: list[float]) -> list[float]:
        # Slightly different heuristic weighting than LightGBM
        rsi_norm = features[0] if len(features)>0 else 0
        adx = features[1] if len(features)>1 else 0.3
        dist_ema20 = features[8] if len(features)>8 else 0
        dist_vwap = features[7] if len(features)>7 else 0
        pcr_dev = features[15] if len(features)>15 else 0
        call_dist = features[16] if len(features)>16 else 0
        put_dist = features[17] if len(features)>17 else 0
        # XGBoost style: more weight to price structure
        score = 0.20*rsi_norm + 0.20*math.tanh(dist_ema20*1.2) + 0.15*math.tanh(dist_vwap*1.1) + 0.12*pcr_dev*0.6 + 0.08*(put_dist - call_dist) + 0.1*(adx-0.4)
        if score>0:
            up_logit=1.1 + score*2.2*(0.6+0.4*adx)
            down_logit=0.9 - score*1.4
            side_logit=1.0+(1-adx)*1.0
        else:
            up_logit=0.9 + score*1.4
            down_logit=1.1 - score*2.2*(0.6+0.4*adx)
            side_logit=1.0+(1-adx)*1.0
        exp_up=math.exp(max(-5,min(5,up_logit)))
        exp_down=math.exp(max(-5,min(5,down_logit)))
        exp_side=math.exp(max(-5,min(5,side_logit)))
        total=exp_up+exp_down+exp_side
        return [exp_up/total, exp_side/total, exp_down/total]

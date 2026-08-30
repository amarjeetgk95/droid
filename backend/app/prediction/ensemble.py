from app.prediction.models.lightgbm_model import LightGBMModel
from app.prediction.models.xgboost_model import XGBoostModel

class EnsembleModel:
    def __init__(self, w_lgb: float=0.5, w_xgb: float=0.5):
        self.lgb=LightGBMModel()
        self.xgb=XGBoostModel()
        self.w_lgb=w_lgb
        self.w_xgb=w_xgb
        self.version="ensemble-v1"

    def predict(self, features: list[float]) -> dict:
        p_lgb=self.lgb.predict_proba(features) # [up, side, down]
        p_xgb=self.xgb.predict_proba(features)
        # weighted average
        up = self.w_lgb*p_lgb[0] + self.w_xgb*p_xgb[0]
        side = self.w_lgb*p_lgb[1] + self.w_xgb*p_xgb[1]
        down = self.w_lgb*p_lgb[2] + self.w_xgb*p_xgb[2]
        # normalize
        total=up+side+down
        up/=total; side/=total; down/=total
        # expected move % and range placeholder (derived from volatility)
        # will be refined in predictor using ATR
        return {
            "up": round(up,4),
            "sideways": round(side,4),
            "down": round(down,4),
            "lgb": [round(x,4) for x in p_lgb],
            "xgb": [round(x,4) for x in p_xgb],
            "ensemble_weights": {"lgb": self.w_lgb, "xgb": self.w_xgb},
        }

    def predict_with_meta(self, features: list[float], instrument: str, asset_class: str, timeframe: str, model_version="v1", feature_version="v1") -> dict:
        pred=self.predict(features)
        return {
            **pred,
            "instrument": instrument,
            "asset_class": asset_class,
            "timeframe": timeframe,
            "model_version": model_version,
            "feature_version": feature_version,
        }

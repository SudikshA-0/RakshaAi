"""Live risk scorer.

Loads the two trained XGBoost models once and, for each transaction, returns
fraud & chargeback probabilities plus SHAP-style reason codes. Reason codes are
computed with XGBoost's native ``pred_contribs`` (exact tree SHAP values) so we
don't depend on the shap library at request time.
"""
from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
import pandas as pd
import xgboost as xgb
from xgboost import XGBClassifier

from ..config import ARTIFACTS_DIR
from .features import FEATURE_COLUMNS, FEATURE_LABELS, build_features


class RiskScorer:
    def __init__(self):
        meta = json.loads((ARTIFACTS_DIR / "metadata.json").read_text())
        self.feature_columns = meta["feature_columns"]
        self.fraud_threshold = meta["fraud_threshold"]
        self.chargeback_threshold = meta["chargeback_threshold"]
        # Stamp every decision with the model version for auditability.
        self.model_version = str(meta.get("trained_at") or "unknown")

        self.fraud_model = XGBClassifier()
        self.fraud_model.load_model(ARTIFACTS_DIR / "fraud_model.json")
        self.cb_model = XGBClassifier()
        self.cb_model.load_model(ARTIFACTS_DIR / "chargeback_model.json")
        self._fraud_booster = self.fraud_model.get_booster()

    def score(self, txn: dict, ctx: dict) -> dict:
        feats = build_features(txn, ctx)
        X = pd.DataFrame([feats])[self.feature_columns]

        fraud_score = float(self.fraud_model.predict_proba(X)[0, 1])
        chargeback_score = float(self.cb_model.predict_proba(X)[0, 1])
        reasons = self._reason_codes(X, feats)

        return {
            "fraud_score": fraud_score,
            "chargeback_score": chargeback_score,
            "reason_codes": reasons,
            "features": feats,
        }

    def _reason_codes(self, X: pd.DataFrame, feats: dict, top_k: int = 6) -> list[dict]:
        dm = xgb.DMatrix(X, feature_names=self.feature_columns)
        contribs = self._fraud_booster.predict(dm, pred_contribs=True)[0]
        # last element is the bias term
        pairs = list(zip(self.feature_columns, contribs[:-1]))
        pairs.sort(key=lambda p: abs(p[1]), reverse=True)

        reasons = []
        for feat, impact in pairs[:top_k]:
            if abs(impact) < 0.02:
                continue
            reasons.append({
                "feature": feat,
                "label": FEATURE_LABELS.get(feat, feat),
                "value": round(float(feats[feat]), 3),
                "impact": round(float(impact), 4),
                "direction": "increases" if impact > 0 else "decreases",
            })
        return reasons


@lru_cache(maxsize=1)
def get_scorer() -> RiskScorer:
    return RiskScorer()

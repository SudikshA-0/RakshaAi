"""Training pipeline.

Trains two gradient-boosted models on a *temporal* split (train on the past,
test on the future — the only honest way to evaluate a fraud model), then:
  * measures precision / recall / F1 / PR-AUC / ROC-AUC on the held-out set,
  * sweeps the decision threshold to find the point that minimises real
    rupee loss (missed-fraud cost vs false-positive cost), and
  * extracts SHAP global importances.
Artifacts are written to app/ml/artifacts/ for the live scorer to load.
"""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.metrics import (average_precision_score, confusion_matrix,
                            f1_score, precision_recall_curve, precision_score,
                            recall_score, roc_auc_score)
from xgboost import XGBClassifier

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.config import (ARTIFACTS_DIR, CHARGEBACK_FEE, DATA_DIR,
                        FALSE_POSITIVE_FRICTION, FALSE_POSITIVE_MARGIN,
                        RANDOM_SEED, TEST_FRACTION)
from app.ml.features import FEATURE_COLUMNS, FEATURE_LABELS


def train_model(X_train, y_train):
    pos = max(int(y_train.sum()), 1)
    neg = int((y_train == 0).sum())
    model = XGBClassifier(
        n_estimators=350, max_depth=5, learning_rate=0.07,
        subsample=0.9, colsample_bytree=0.85, reg_lambda=1.2,
        min_child_weight=2, eval_metric="aucpr", tree_method="hist",
        scale_pos_weight=neg / pos, n_jobs=-1, random_state=RANDOM_SEED,
    )
    model.fit(X_train, y_train)
    return model


def basic_metrics(y_true, proba, thr):
    pred = (proba >= thr).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    return {
        "precision": float(precision_score(y_true, pred, zero_division=0)),
        "recall": float(recall_score(y_true, pred, zero_division=0)),
        "f1": float(f1_score(y_true, pred, zero_division=0)),
        "pr_auc": float(average_precision_score(y_true, proba)),
        "roc_auc": float(roc_auc_score(y_true, proba)),
        "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def cost_sweep(y_true, proba, amounts):
    """For each candidate threshold compute the total expected rupee loss.

    missed fraud  -> amount + chargeback fee
    false block   -> lost margin on the order + fixed friction
    Returns the full curve plus the loss-minimising threshold.
    """
    y_true = np.asarray(y_true)
    amounts = np.asarray(amounts, dtype=float)
    fraud_loss = amounts + CHARGEBACK_FEE
    fp_loss = amounts * FALSE_POSITIVE_MARGIN + FALSE_POSITIVE_FRICTION

    curve = []
    for thr in np.linspace(0.02, 0.98, 97):
        pred = proba >= thr
        fn_cost = fraud_loss[(y_true == 1) & (~pred)].sum()
        fp_cost = fp_loss[(y_true == 0) & (pred)].sum()
        total = float(fn_cost + fp_cost)
        pr = precision_score(y_true, pred.astype(int), zero_division=0)
        rc = recall_score(y_true, pred.astype(int), zero_division=0)
        curve.append({"threshold": round(float(thr), 3), "cost": round(total, 2),
                      "precision": round(float(pr), 4), "recall": round(float(rc), 4)})

    best = min(curve, key=lambda p: p["cost"])
    baseline = float(fraud_loss[y_true == 1].sum())        # allow everything
    naive = next(p["cost"] for p in curve if abs(p["threshold"] - 0.5) < 0.011)
    return {
        "cost_curve": curve,
        "threshold": best["threshold"],
        "optimized_cost": best["cost"],
        "baseline_cost": round(baseline, 2),
        "naive_cost": round(float(naive), 2),
        "savings": round(baseline - best["cost"], 2),
        "savings_vs_naive": round(float(naive) - best["cost"], 2),
    }


def shap_importance(model, X_sample) -> list[dict]:
    try:
        import shap
        explainer = shap.TreeExplainer(model)
        vals = explainer.shap_values(X_sample)
        if isinstance(vals, list):
            vals = vals[-1]
        imp = np.abs(vals).mean(axis=0)
    except Exception as exc:  # pragma: no cover - fallback path
        print(f"  (shap unavailable: {exc}; using gain importance)")
        imp = model.feature_importances_
    order = np.argsort(imp)[::-1]
    return [{"feature": FEATURE_COLUMNS[i], "label": FEATURE_LABELS[FEATURE_COLUMNS[i]],
             "importance": float(imp[i])} for i in order]


def pr_curve_points(y_true, proba, n=60):
    prec, rec, _ = precision_recall_curve(y_true, proba)
    idx = np.linspace(0, len(prec) - 1, n).astype(int)
    return [{"recall": round(float(rec[i]), 4), "precision": round(float(prec[i]), 4)}
            for i in idx]


def main():
    df = pd.read_csv(DATA_DIR / "transactions.csv", parse_dates=["ts"])
    df = df.sort_values("ts").reset_index(drop=True)

    split = int(len(df) * (1 - TEST_FRACTION))
    train_df, test_df = df.iloc[:split], df.iloc[split:]
    X_train, X_test = train_df[FEATURE_COLUMNS], test_df[FEATURE_COLUMNS]
    print(f"Temporal split: {len(train_df):,} train / {len(test_df):,} test")

    # ---- Fraud model ---------------------------------------------------------
    print("Training fraud model ...")
    fraud_model = train_model(X_train, train_df["is_fraud"])
    fraud_proba = fraud_model.predict_proba(X_test)[:, 1]
    cost = cost_sweep(test_df["is_fraud"], fraud_proba, test_df["amount"])
    fraud_metrics = basic_metrics(test_df["is_fraud"], fraud_proba, cost["threshold"])
    fraud_metrics.update({k: cost[k] for k in
                          ("threshold", "cost_curve", "optimized_cost",
                           "baseline_cost", "naive_cost", "savings", "savings_vs_naive")})
    fraud_metrics["pr_curve"] = pr_curve_points(test_df["is_fraud"], fraud_proba)

    # ---- Chargeback model ----------------------------------------------------
    print("Training chargeback model ...")
    cb_model = train_model(X_train, train_df["is_chargeback"])
    cb_proba = cb_model.predict_proba(X_test)[:, 1]
    cb_cost = cost_sweep(test_df["is_chargeback"], cb_proba, test_df["amount"])
    cb_metrics = basic_metrics(test_df["is_chargeback"], cb_proba, cb_cost["threshold"])
    cb_metrics.update({"threshold": cb_cost["threshold"],
                       "pr_curve": pr_curve_points(test_df["is_chargeback"], cb_proba)})

    # ---- Explainability ------------------------------------------------------
    print("Computing SHAP importances ...")
    sample = X_test.sample(min(1500, len(X_test)), random_state=RANDOM_SEED)
    importance = shap_importance(fraud_model, sample)

    # ---- Persist -------------------------------------------------------------
    fraud_model.save_model(ARTIFACTS_DIR / "fraud_model.json")
    cb_model.save_model(ARTIFACTS_DIR / "chargeback_model.json")

    metadata = {
        "feature_columns": FEATURE_COLUMNS,
        "fraud_threshold": cost["threshold"],
        "chargeback_threshold": cb_cost["threshold"],
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_train": len(train_df), "n_test": len(test_df),
        "cost_params": {"chargeback_fee": CHARGEBACK_FEE,
                        "fp_margin": FALSE_POSITIVE_MARGIN,
                        "fp_friction": FALSE_POSITIVE_FRICTION},
    }
    (ARTIFACTS_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2))

    metrics = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_train": len(train_df), "n_test": len(test_df),
        "fraud_rate_train": float(train_df["is_fraud"].mean()),
        "fraud_rate_test": float(test_df["is_fraud"].mean()),
        "chargeback_rate_test": float(test_df["is_chargeback"].mean()),
        "fraud": fraud_metrics,
        "chargeback": cb_metrics,
        "feature_importance": importance,
    }
    (ARTIFACTS_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))

    print("\n=== Fraud model (held-out) ===")
    print(f"  precision {fraud_metrics['precision']:.3f} | recall "
          f"{fraud_metrics['recall']:.3f} | F1 {fraud_metrics['f1']:.3f} | "
          f"PR-AUC {fraud_metrics['pr_auc']:.3f} | ROC-AUC {fraud_metrics['roc_auc']:.3f}")
    print(f"  cost-optimal threshold: {cost['threshold']:.2f}")
    print(f"  loss if we allowed everything : Rs {cost['baseline_cost']:,.0f}")
    print(f"  loss at optimal threshold     : Rs {cost['optimized_cost']:,.0f}")
    print(f"  => money saved                : Rs {cost['savings']:,.0f}")
    print(f"\n=== Chargeback model (held-out) ===")
    print(f"  precision {cb_metrics['precision']:.3f} | recall "
          f"{cb_metrics['recall']:.3f} | PR-AUC {cb_metrics['pr_auc']:.3f}")
    print("\nArtifacts written to", ARTIFACTS_DIR)


if __name__ == "__main__":
    main()

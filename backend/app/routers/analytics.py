"""Analytics endpoints — all metrics computed live from stored decisions and
ground-truth labels. Nothing here is hard-coded."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import (ARTIFACTS_DIR, FALSE_POSITIVE_FRICTION,
                      FALSE_POSITIVE_MARGIN, potential_loss as loss_at_risk,
                      prevented_loss)
from ..database import get_db
from ..dependencies import get_current_org
from ..models import Decision, Organization, Transaction

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _pct(a, b):
    return round(100.0 * a / b, 2) if b else 0.0


def _model_action(row) -> str:
    return row.original_model_action or row.action or "ALLOW"


def _empty_overview():
    return {
        "total_transactions": 0,
        "total_amount": 0.0,
        "action_counts": {a: 0 for a in ("ALLOW", "STEP_UP", "HOLD", "BLOCK")},
        "flagged": 0,
        "flag_rate": 0.0,
        "block_rate": 0.0,
        "detection_rate": 0.0,
        "precision": 0.0,
        "false_positive_rate": 0.0,
        "confusion": {"tp": 0, "fp": 0, "fn": 0, "tn": 0},
        "total_fraud": 0,
        "fraud_caught": 0,
        "fraud_missed": 0,
        "false_positives": 0,
        "potential_loss": 0.0,
        "money_saved": 0.0,
        "leaked_loss": 0.0,
        "false_positive_cost": 0.0,
        "net_benefit": 0.0,
        "chargeback_value_at_risk": 0.0,
        "avg_latency_ms": 0.0,
        "p95_latency_ms": 0.0,
        "ring_incidents": 0,
        "pending_review": 0,
        "analyst_overrides": 0,
        "analyst_override_rate": 0.0,
        "analyst_labeled": 0,
    }


@router.get("/overview")
def overview(db: Session = Depends(get_db),
             org: Organization = Depends(get_current_org)):
    rows = db.execute(
        select(Transaction.amount, Transaction.is_fraud, Transaction.is_chargeback,
               Decision.action, Decision.original_model_action, Decision.final_action,
               Decision.analyst_override, Decision.analyst_label,
               Decision.latency_ms, Decision.ring_flag, Decision.status)
        .join(Decision, Decision.txn_id == Transaction.id)
        .where(Transaction.org_id == org.id)
    ).all()
    n = len(rows)
    if n == 0:
        return _empty_overview()

    # Operational mix uses the analyst-final action; model quality uses original.
    actions = Counter((r.final_action or r.action) for r in rows)
    allowed = actions.get("ALLOW", 0)
    flagged = n - allowed

    tp = sum(1 for r in rows if _model_action(r) != "ALLOW" and r.is_fraud == 1)
    fp = sum(1 for r in rows if _model_action(r) != "ALLOW" and r.is_fraud == 0)
    fn = sum(1 for r in rows if _model_action(r) == "ALLOW" and r.is_fraud == 1)
    tn = sum(1 for r in rows if _model_action(r) == "ALLOW" and r.is_fraud == 0)
    total_fraud = tp + fn
    total_legit = fp + tn

    potential = sum(loss_at_risk(r.amount) for r in rows if r.is_fraud == 1)
    confirmed_saved = sum(prevented_loss(r.amount, _model_action(r), r.is_fraud)
                          for r in rows)
    fp_cost = sum(r.amount * FALSE_POSITIVE_MARGIN + FALSE_POSITIVE_FRICTION
                  for r in rows if _model_action(r) != "ALLOW" and r.is_fraud == 0)
    labeled = sum(1 for r in rows if r.analyst_label is not None)
    overrides = sum(1 for r in rows if r.analyst_override)

    latencies = sorted(r.latency_ms for r in rows)
    p95 = latencies[int(0.95 * (len(latencies) - 1))] if latencies else 0.0

    total_amount = sum(r.amount for r in rows)
    cb_value_at_risk = sum(loss_at_risk(r.amount) for r in rows if r.is_chargeback == 1)

    return {
        "total_transactions": n,
        "total_amount": round(total_amount, 2),
        "action_counts": {a: actions.get(a, 0)
                          for a in ("ALLOW", "STEP_UP", "HOLD", "BLOCK")},
        "flagged": flagged,
        "flag_rate": _pct(flagged, n),
        "block_rate": _pct(actions.get("BLOCK", 0), n),
        # live decision quality vs ground truth — original model action only
        "detection_rate": _pct(tp, total_fraud),      # recall
        "precision": _pct(tp, tp + fp),
        "false_positive_rate": _pct(fp, total_legit),
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "total_fraud": total_fraud,
        "fraud_caught": tp,
        "fraud_missed": fn,
        "false_positives": fp,
        # money — same formula as timeseries
        "potential_loss": round(potential, 2),
        "money_saved": round(confirmed_saved, 2),
        "leaked_loss": round(potential - confirmed_saved, 2),
        "false_positive_cost": round(fp_cost, 2),
        "net_benefit": round(confirmed_saved - fp_cost, 2),
        "chargeback_value_at_risk": round(cb_value_at_risk, 2),
        # ops
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
        "p95_latency_ms": round(p95, 2),
        "ring_incidents": sum(1 for r in rows if r.ring_flag),
        "pending_review": sum(1 for r in rows if r.status == "pending_review"),
        "analyst_overrides": overrides,
        "analyst_override_rate": _pct(overrides, labeled),
        "analyst_labeled": labeled,
    }


@router.get("/timeseries")
def timeseries(db: Session = Depends(get_db),
               org: Organization = Depends(get_current_org),
               days: int = Query(14, ge=1, le=60)):
    rows = db.execute(
        select(Transaction.ts, Transaction.is_fraud, Transaction.amount,
               Decision.action, Decision.original_model_action)
        .join(Decision, Decision.txn_id == Transaction.id)
        .where(Transaction.org_id == org.id)
    ).all()
    if not rows:
        return {"series": []}

    max_day = max(r.ts.date() for r in rows)
    start = max_day - timedelta(days=days - 1)
    buckets: dict = defaultdict(lambda: {"volume": 0, "fraud": 0, "blocked": 0,
                                         "amount": 0.0, "saved": 0.0})
    for r in rows:
        d = r.ts.date()
        if d < start:
            continue
        b = buckets[d.isoformat()]
        b["volume"] += 1
        b["amount"] += r.amount
        model_act = _model_action(r)
        if r.is_fraud == 1:
            b["fraud"] += 1
            b["saved"] += prevented_loss(r.amount, model_act, 1)
        if model_act == "BLOCK":
            b["blocked"] += 1

    series = []
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        b = buckets.get(d, {"volume": 0, "fraud": 0, "blocked": 0, "amount": 0.0, "saved": 0.0})
        series.append({"date": d, **{k: round(v, 2) for k, v in b.items()}})
    return {"series": series}


@router.get("/risk-drivers")
def risk_drivers(db: Session = Depends(get_db),
                 org: Organization = Depends(get_current_org),
                 limit: int = 1000):
    decisions = db.execute(
        select(Decision.reason_codes)
        .where(Decision.org_id == org.id)
        .order_by(Decision.id.desc()).limit(limit)
    ).scalars().all()
    tally: Counter = Counter()
    for reasons in decisions:
        for rc in (reasons or []):
            if rc.get("direction") == "increases":
                tally[rc["label"]] += 1
    drivers = [{"label": k, "count": v} for k, v in tally.most_common(8)]
    return {"drivers": drivers}


@router.get("/threat-patterns")
def threat_patterns(db: Session = Depends(get_db),
                    org: Organization = Depends(get_current_org)):
    rows = db.execute(
        select(Transaction.fraud_pattern, Transaction.amount)
        .where(Transaction.org_id == org.id, Transaction.is_fraud == 1)
    ).all()
    counts: Counter = Counter()
    value: dict = defaultdict(float)
    for r in rows:
        counts[r.fraud_pattern] += 1
        value[r.fraud_pattern] += loss_at_risk(r.amount)
    return {"patterns": [{"pattern": k, "count": v, "value_at_risk": round(value[k], 2)}
                         for k, v in counts.most_common()]}


@router.get("/model")
def model_performance(org: Organization = Depends(get_current_org)):
    metrics_path = ARTIFACTS_DIR / "metrics.json"
    meta_path = ARTIFACTS_DIR / "metadata.json"
    if not metrics_path.exists():
        return {"available": False}
    metrics = json.loads(metrics_path.read_text())
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    metrics["available"] = True
    metrics["metadata"] = meta
    return metrics

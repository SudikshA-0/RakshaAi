"""Case-management (manual review queue) endpoints and the analyst feedback
loop that records overrides for future retraining."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_org
from ..models import Decision, Feedback, Organization, Transaction
from ..schemas import FeedbackIn
from ..services.pipeline import serialize

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.get("")
def list_cases(db: Session = Depends(get_db),
               org: Organization = Depends(get_current_org),
               resolved: bool = False,
               limit: int = Query(100, ge=1, le=500)):
    status_filter = "resolved" if resolved else "pending_review"
    rows = db.execute(
        select(Transaction, Decision).join(Decision, Decision.txn_id == Transaction.id)
        .where(Decision.org_id == org.id, Decision.status == status_filter)
        .order_by(Decision.risk_score.desc()).limit(limit)
    ).all()
    return {"cases": [serialize(t, d) for t, d in rows]}


@router.post("/{decision_id}/resolve")
def resolve_case(decision_id: int, payload: FeedbackIn, db: Session = Depends(get_db),
                 org: Organization = Depends(get_current_org)):
    decision = db.get(Decision, decision_id)
    if not decision or decision.org_id != org.id:
        raise HTTPException(404, "Decision not found")

    original = decision.original_model_action or decision.action
    final = "BLOCK" if payload.analyst_label == 1 else "ALLOW"

    decision.analyst_label = payload.analyst_label
    decision.status = "resolved"
    decision.resolved_at = datetime.utcnow()
    # Analyst outcome is stored separately — the original model decision is immutable.
    decision.final_action = final
    decision.action = final
    decision.analyst_override = original != final
    if not decision.original_model_action:
        decision.original_model_action = original

    db.add(Feedback(org_id=org.id, decision_id=decision.id, txn_id=decision.txn_id,
                    analyst_label=payload.analyst_label, note=payload.note))
    db.commit()

    row = db.execute(
        select(Transaction, Decision).join(Decision, Decision.txn_id == Transaction.id)
        .where(Decision.id == decision_id, Decision.org_id == org.id)
    ).first()
    return serialize(row[0], row[1])


@router.get("/feedback/summary")
def feedback_summary(db: Session = Depends(get_db),
                     org: Organization = Depends(get_current_org)):
    """The learning loop, quantified: how analyst overrides would retrain the model."""
    fb = db.execute(
        select(Feedback).where(Feedback.org_id == org.id)
        .order_by(Feedback.created_at.desc())
    ).scalars().all()
    confirmed_fraud = sum(1 for f in fb if f.analyst_label == 1)
    confirmed_legit = sum(1 for f in fb if f.analyst_label == 0)
    overrides = db.execute(
        select(Decision).where(Decision.org_id == org.id,
                               Decision.analyst_override.is_(True))
    ).scalars().all()
    return {
        "total_feedback": len(fb),
        "confirmed_fraud": confirmed_fraud,
        "confirmed_legit_released": confirmed_legit,
        "analyst_overrides": len(overrides),
        "recent": [{"txn_id": f.txn_id, "label": f.analyst_label, "note": f.note,
                    "at": f.created_at.isoformat() if f.created_at else None}
                   for f in fb[:15]],
    }

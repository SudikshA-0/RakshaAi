"""Simulation endpoints that drive the live demo: a steady stream of realistic
traffic and scripted coordinated-attack bursts. Everything flows through the
same scoring pipeline as real ingestion."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from ..config import prevented_loss
from ..database import get_db
from ..dependencies import get_current_org
from ..models import Organization
from ..schemas import AttackRequest
from ..services import simulator
from ..services.pipeline import ingest_and_score, serialize
from ..services.webhooks import enqueue_decision_webhooks

router = APIRouter(prefix="/api/simulate", tags=["simulate"])


@router.post("/transaction")
def simulate_one(background_tasks: BackgroundTasks,
                 db: Session = Depends(get_db),
                 org: Organization = Depends(get_current_org)):
    raw = simulator.random_transaction(db, org.id)
    txn, decision = ingest_and_score(db, raw, org.id, source="live")
    enqueue_decision_webhooks(db, txn, decision, background_tasks)
    return serialize(txn, decision)


@router.post("/batch")
def simulate_batch(background_tasks: BackgroundTasks,
                   db: Session = Depends(get_db),
                   org: Organization = Depends(get_current_org),
                   n: int = Query(6, ge=1, le=30)):
    out = []
    for _ in range(n):
        raw = simulator.random_transaction(db, org.id)
        txn, decision = ingest_and_score(db, raw, org.id, source="live", commit=False)
        out.append((txn, decision))
    db.commit()
    for txn, decision in out:
        enqueue_decision_webhooks(db, txn, decision, background_tasks)
    return {"transactions": [serialize(t, d) for t, d in out]}


@router.post("/attack")
def simulate_attack(payload: AttackRequest, background_tasks: BackgroundTasks,
                    db: Session = Depends(get_db),
                    org: Organization = Depends(get_current_org)):
    try:
        burst = simulator.attack_burst(payload.kind, payload.count, db=db, org_id=org.id)
        results = []
        for raw in burst:
            txn, decision = ingest_and_score(db, raw, org.id, source="attack", commit=False)
            results.append((txn, decision))
        db.commit()
    except Exception:
        db.rollback()
        raise

    for txn, decision in results:
        enqueue_decision_webhooks(db, txn, decision, background_tasks)

    serialized = [serialize(t, d) for t, d in results]
    blocked = sum(1 for s in serialized if s["original_model_action"] == "BLOCK")
    held = sum(1 for s in serialized if s["original_model_action"] == "HOLD")
    stepped = sum(1 for s in serialized if s["original_model_action"] == "STEP_UP")
    saved = sum(prevented_loss(s["amount"], s["original_model_action"], s["is_fraud"])
                for s in serialized)
    stopped = blocked + held
    return {
        "kind": payload.kind,
        "count": len(serialized),
        "blocked": blocked,
        "held": held,
        "stepped_up": stepped,
        "stopped": stopped,
        "stop_rate": round(100.0 * stopped / len(serialized), 1) if serialized else 0,
        "loss_prevented": round(saved, 2),
        "ring_detected": any(s["ring_flag"] for s in serialized),
        "ring_size": max((s["ring_size"] for s in serialized), default=0),
        "transactions": serialized,
    }

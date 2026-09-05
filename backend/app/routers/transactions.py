"""Transaction ingestion, listing and detail endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_org
from ..models import Decision, Organization, Transaction
from ..schemas import TransactionIn
from ..services.pipeline import ingest_and_score, serialize
from ..services.webhooks import enqueue_decision_webhooks

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.post("")
def ingest(payload: TransactionIn, background_tasks: BackgroundTasks,
           db: Session = Depends(get_db),
           org: Organization = Depends(get_current_org)):
    raw = payload.model_dump()
    raw["ts"] = raw.get("ts") or datetime.utcnow()
    txn, decision = ingest_and_score(db, raw, org.id, source="live")
    enqueue_decision_webhooks(db, txn, decision, background_tasks)
    return serialize(txn, decision)


@router.get("")
def list_transactions(
    db: Session = Depends(get_db),
    org: Organization = Depends(get_current_org),
    limit: int = Query(60, ge=1, le=500),
    offset: int = Query(0, ge=0),
    action: str | None = None,
    status: str | None = None,
    source: str | None = None,
    min_risk: float | None = None,
    ring_only: bool = False,
    q: str | None = None,
):
    stmt = (select(Transaction, Decision)
            .join(Decision, Decision.txn_id == Transaction.id)
            .where(Transaction.org_id == org.id))
    if action:
        stmt = stmt.where(Decision.action == action.upper())
    if status:
        stmt = stmt.where(Decision.status == status)
    if source:
        stmt = stmt.where(Transaction.source == source)
    if min_risk is not None:
        stmt = stmt.where(Decision.risk_score >= min_risk)
    if ring_only:
        stmt = stmt.where(Decision.ring_flag.is_(True))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            (Transaction.txn_ref.ilike(like)) | (Transaction.customer_id.ilike(like))
            | (Transaction.device_id.ilike(like)) | (Transaction.email.ilike(like)))
    stmt = stmt.order_by(Transaction.id.desc()).limit(limit).offset(offset)

    rows = db.execute(stmt).all()
    return {"transactions": [serialize(t, d) for t, d in rows]}


@router.get("/{txn_id}")
def get_transaction(txn_id: int, db: Session = Depends(get_db),
                    org: Organization = Depends(get_current_org)):
    row = db.execute(
        select(Transaction, Decision).join(Decision, Decision.txn_id == Transaction.id)
        .where(Transaction.id == txn_id, Transaction.org_id == org.id)
    ).first()
    if not row:
        raise HTTPException(404, "Transaction not found")
    data = serialize(row[0], row[1])

    # linked entities on the same device (ring context) — same tenant only
    linked = db.execute(
        select(Transaction, Decision).join(Decision, Decision.txn_id == Transaction.id)
        .where(Transaction.org_id == org.id,
               Transaction.device_id == row[0].device_id,
               Transaction.id != txn_id)
        .order_by(Transaction.id.desc()).limit(8)
    ).all()
    data["linked_transactions"] = [serialize(t, d) for t, d in linked]
    return data

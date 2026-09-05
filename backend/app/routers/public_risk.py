"""Versioned public merchant integration API."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_api_key
from ..models import APIKey
from ..schemas import TransactionIn
from ..services.pipeline import ingest_and_score
from ..services.webhooks import enqueue_decision_webhooks

router = APIRouter(prefix="/api/v1/risk", tags=["public risk api"])


@router.post("/score")
def score(payload: TransactionIn, background_tasks: BackgroundTasks,
          db: Session = Depends(get_db),
          key: APIKey = Depends(get_api_key)):
    """Score and persist one merchant transaction using its API key's tenant."""
    raw = payload.model_dump()
    raw["ts"] = raw.get("ts") or datetime.utcnow()
    source = "api_sandbox" if key.environment == "sandbox" else "api_live"
    txn, decision = ingest_and_score(db, raw, key.org_id, source=source)
    enqueue_decision_webhooks(db, txn, decision, background_tasks)
    return {
        "request_id": txn.txn_ref,
        "transaction_id": txn.id,
        "fraud_probability": decision.fraud_score,
        "chargeback_probability": decision.chargeback_score,
        "risk_score": decision.risk_score,
        "decision": decision.final_action or decision.action,
        "original_model_action": decision.original_model_action or decision.action,
        "reason_codes": decision.reason_codes,
        "model_version": decision.model_version,
        "risk_signals": {"ring_flag": decision.ring_flag, "ring_size": decision.ring_size},
    }

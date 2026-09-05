"""End-to-end scoring pipeline: the single code path that turns a raw
transaction into a persisted, scored, decided record. Used by the live ingest
API, the simulator, and the historical seeder so behaviour is identical
everywhere.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import DEFAULT_POLICY
from ..ml.features import email_domain_class  # noqa: F401 (kept for parity)
from ..ml.scorer import get_scorer
from ..models import Decision, Policy, Transaction
from .decision import decide
from .velocity import compute_context


def make_ref() -> str:
    return "TXN" + uuid.uuid4().hex[:12].upper()


def get_policy_row(db: Session, org_id: int) -> Policy:
    """Fetch (or lazily create) the risk policy for one organization."""
    policy = db.execute(
        select(Policy).where(Policy.org_id == org_id)
    ).scalar_one_or_none()
    if policy is None:
        policy = Policy(org_id=org_id, **DEFAULT_POLICY)
        db.add(policy)
        db.commit()
        db.refresh(policy)
    return policy


def policy_to_dict(policy: Policy) -> dict:
    return {
        "risk_appetite": policy.risk_appetite,
        "block_threshold": policy.block_threshold,
        "review_threshold": policy.review_threshold,
        "challenge_threshold": policy.challenge_threshold,
        "chargeback_weight": policy.chargeback_weight,
        "auto_block_enabled": policy.auto_block_enabled,
    }


def ingest_and_score(db: Session, raw: dict, org_id: int, source: str = "live",
                     commit: bool = True) -> tuple[Transaction, Decision]:
    """Score one raw transaction and persist Transaction + Decision.

    ``org_id`` scopes the transaction to a single merchant tenant — velocity,
    ring detection and policy are all resolved within that tenant only.

    ``raw`` may include ground-truth labels (is_fraud/is_chargeback/
    fraud_pattern) for synthetic data; they are stored for evaluation only and
    never passed to the model.
    """
    raw = dict(raw)
    raw.setdefault("ts", datetime.utcnow())
    if isinstance(raw["ts"], str):
        raw["ts"] = datetime.fromisoformat(raw["ts"])
    raw.setdefault("email", "unknown@unknown")
    raw["email_domain"] = raw.get("email_domain") or raw["email"].split("@")[-1]

    t0 = time.perf_counter()
    ctx = compute_context(db, raw, org_id)
    scorer = get_scorer()
    scored = scorer.score(raw, ctx)
    policy = policy_to_dict(get_policy_row(db, org_id))
    verdict = decide(scored["fraud_score"], scored["chargeback_score"], ctx,
                     policy, float(raw["amount"]))
    latency_ms = (time.perf_counter() - t0) * 1000.0

    txn = Transaction(
        org_id=org_id,
        txn_ref=raw.get("txn_ref") or make_ref(),
        ts=raw["ts"],
        customer_id=str(raw.get("customer_id", "GUEST")),
        card_hash=str(raw["card_hash"]),
        card_bin=str(raw.get("card_bin", "400000")),
        card_type=str(raw.get("card_type", "credit")),
        device_id=str(raw["device_id"]),
        ip=str(raw.get("ip", "0.0.0.0")),
        email=str(raw["email"]),
        email_domain=str(raw["email_domain"]),
        amount=float(raw["amount"]),
        currency=str(raw.get("currency", "INR")),
        category=str(raw.get("category", "other")),
        channel=str(raw.get("channel", "web")),
        billing_country=str(raw.get("billing_country", "IN")),
        shipping_country=str(raw.get("shipping_country", raw.get("billing_country", "IN"))),
        account_age_days=int(raw.get("account_age_days", 365)),
        is_fraud=int(raw.get("is_fraud", 0)),
        is_chargeback=int(raw.get("is_chargeback", 0)),
        fraud_pattern=str(raw.get("fraud_pattern", "legit")),
        source=source,
    )
    db.add(txn)
    db.flush()  # assign txn.id and make it visible to later velocity queries

    decision = Decision(
        org_id=org_id,
        txn_id=txn.id,
        fraud_score=scored["fraud_score"],
        chargeback_score=scored["chargeback_score"],
        risk_score=verdict["risk_score"],
        model_version=scorer.model_version,
        action=verdict["action"],
        original_model_action=verdict["action"],
        final_action=verdict["action"],
        analyst_override=False,
        status=verdict["status"],
        threshold_block=verdict["thresholds"]["block"],
        threshold_review=verdict["thresholds"]["review"],
        threshold_challenge=verdict["thresholds"]["challenge"],
        expected_loss=verdict["expected_loss"],
        expected_loss_prevented=verdict["expected_loss_prevented"],
        reason_codes=scored["reason_codes"],
        ring_flag=verdict["ring_flag"],
        ring_size=verdict["ring_size"],
        latency_ms=round(latency_ms, 2),
    )
    db.add(decision)
    if commit:
        db.commit()
        db.refresh(txn)
        db.refresh(decision)
    return txn, decision


# --- serialization ---------------------------------------------------------
def serialize(txn: Transaction, decision: Decision) -> dict:
    return {
        "id": txn.id,
        "txn_ref": txn.txn_ref,
        "ts": txn.ts.isoformat(),
        "amount": txn.amount,
        "currency": txn.currency,
        "customer_id": txn.customer_id,
        "card_bin": txn.card_bin,
        "card_last4": str(abs(hash(txn.card_hash)))[-4:],
        "card_type": txn.card_type,
        "device_id": txn.device_id,
        "ip": txn.ip,
        "email": txn.email,
        "email_domain": txn.email_domain,
        "category": txn.category,
        "channel": txn.channel,
        "billing_country": txn.billing_country,
        "shipping_country": txn.shipping_country,
        "account_age_days": txn.account_age_days,
        "source": txn.source,
        "is_fraud": txn.is_fraud,
        "is_chargeback": txn.is_chargeback,
        "fraud_pattern": txn.fraud_pattern,
        # decision
        "action": decision.final_action or decision.action,
        "original_model_action": decision.original_model_action or decision.action,
        "final_action": decision.final_action or decision.action,
        "analyst_override": bool(decision.analyst_override),
        "status": decision.status,
        "fraud_score": decision.fraud_score,
        "chargeback_score": decision.chargeback_score,
        "risk_score": decision.risk_score,
        "model_version": decision.model_version,
        "expected_loss": decision.expected_loss,
        "expected_loss_prevented": decision.expected_loss_prevented,
        "ring_flag": decision.ring_flag,
        "ring_size": decision.ring_size,
        "reason_codes": decision.reason_codes,
        "thresholds": {
            "block": decision.threshold_block,
            "review": decision.threshold_review,
            "challenge": decision.threshold_challenge,
        },
        "latency_ms": decision.latency_ms,
        "analyst_label": decision.analyst_label,
        "decision_id": decision.id,
        "created_at": decision.created_at.isoformat() if decision.created_at else None,
    }


def latest_serialized(db: Session, txn_id: int, org_id: int) -> dict:
    row = db.execute(
        select(Transaction, Decision).join(Decision, Decision.txn_id == Transaction.id)
        .where(Transaction.id == txn_id, Transaction.org_id == org_id)
    ).first()
    return serialize(row[0], row[1])

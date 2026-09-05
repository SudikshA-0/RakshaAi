"""Velocity / entity-history context.

Computes the same aggregates the training pipeline built offline, but live from
the transactions already in the database. Every field mirrors the semantics in
``ml_pipeline.generate_data.compute_velocity_features`` so the model sees
consistent inputs (no train/serve skew).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Transaction


def compute_context(db: Session, txn: dict, org_id: int) -> dict:
    """Velocity / entity-history aggregates, scoped to a single merchant.

    ``org_id`` is mandatory: velocity and ring signals must only ever consider
    the calling merchant's own traffic. Without this scope one tenant's card /
    device / IP history would be polluted by (and leak from) another's.
    """
    now: datetime = txn["ts"] if isinstance(txn["ts"], datetime) else datetime.fromisoformat(str(txn["ts"]))
    h1 = now - timedelta(hours=1)
    h24 = now - timedelta(hours=24)

    # --- Card history --------------------------------------------------------
    # NOTE: we use ``<= now`` (not ``<``). The current transaction is scored
    # *before* it is persisted, so it can never count itself — but real-time
    # attack bursts arrive within the same second, and ``<`` would make them
    # invisible to each other. ``<=`` lets the velocity build correctly.
    card_rows = db.execute(
        select(Transaction.ts, Transaction.amount)
        .where(Transaction.org_id == org_id,
               Transaction.card_hash == txn["card_hash"], Transaction.ts <= now)
    ).all()
    card_count = len(card_rows)
    card_avg = sum(r.amount for r in card_rows) / card_count if card_count else txn["amount"]
    last_ts = max((r.ts for r in card_rows), default=None)
    time_since = (now - last_ts).total_seconds() / 3600.0 if last_ts else 720.0
    velocity_card_1h = sum(1 for r in card_rows if r.ts >= h1)
    velocity_card_24h = sum(1 for r in card_rows if r.ts >= h24)

    # --- Device history (24h window for ring signals) ------------------------
    device_rows = db.execute(
        select(Transaction.ts, Transaction.card_hash, Transaction.email)
        .where(Transaction.org_id == org_id,
               Transaction.device_id == txn["device_id"], Transaction.ts <= now,
               Transaction.ts >= h24)
    ).all()
    velocity_device_1h = sum(1 for r in device_rows if r.ts >= h1)
    velocity_device_24h = len(device_rows)
    distinct_cards = {r.card_hash for r in device_rows} | {txn["card_hash"]}
    distinct_emails = {r.email for r in device_rows} | {txn["email"]}

    # --- IP history ----------------------------------------------------------
    ip_1h = db.execute(
        select(Transaction.id).where(Transaction.org_id == org_id,
                                     Transaction.ip == txn["ip"],
                                     Transaction.ts <= now, Transaction.ts >= h1)
    ).all()

    return {
        "card_txn_count": card_count,
        "card_amount_avg": card_avg,
        "time_since_last_txn_hrs": time_since,
        "velocity_card_1h": velocity_card_1h,
        "velocity_card_24h": velocity_card_24h,
        "velocity_device_1h": velocity_device_1h,
        "velocity_device_24h": velocity_device_24h,
        "velocity_ip_1h": len(ip_1h),
        "distinct_cards_device_24h": len(distinct_cards),
        "distinct_emails_device_24h": len(distinct_emails),
    }

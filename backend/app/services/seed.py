"""Seed the database with recent historical transactions, each scored through
the real pipeline (not pre-baked). Run as: ``python -m app.services.seed``.

Seeded rows belong to a single organization (the demo merchant by default), so
seeding never leaks across tenants and the reset only clears that org's data.
"""
from __future__ import annotations

import sys

import pandas as pd

from ..config import DATA_DIR
from ..database import SessionLocal, bootstrap_tenancy, init_db
from ..models import Decision, Feedback, Transaction
from .pipeline import get_policy_row, ingest_and_score

RAW_FIELDS = ["txn_ref", "ts", "customer_id", "card_hash", "card_bin", "card_type",
              "device_id", "ip", "email", "email_domain", "amount", "category",
              "channel", "billing_country", "shipping_country", "account_age_days",
              "is_fraud", "is_chargeback", "fraud_pattern"]


def seed(org_id: int | None = None, n: int = 1800, reset: bool = True) -> int:
    init_db()
    db = SessionLocal()
    try:
        if org_id is None:
            org_id = bootstrap_tenancy().id
        get_policy_row(db, org_id)  # ensure this org's policy exists
        if reset:
            # Only clear THIS org's data — never touch other tenants.
            db.query(Feedback).filter(Feedback.org_id == org_id).delete()
            db.query(Decision).filter(Decision.org_id == org_id).delete()
            db.query(Transaction).filter(Transaction.org_id == org_id).delete()
            db.commit()

        df = pd.read_csv(DATA_DIR / "transactions.csv", parse_dates=["ts"])
        df = df.sort_values("ts").tail(n).reset_index(drop=True)
        print(f"Seeding {len(df):,} transactions through the live scoring pipeline ...")

        for i, row in enumerate(df.itertuples(index=False)):
            raw = {f: getattr(row, f) for f in RAW_FIELDS}
            raw["ts"] = pd.Timestamp(raw["ts"]).to_pydatetime()
            ingest_and_score(db, raw, org_id, source="seed", commit=False)
            if (i + 1) % 400 == 0:
                db.commit()
                print(f"  ... {i + 1:,} scored")
        db.commit()

        total = db.query(Transaction).filter(Transaction.org_id == org_id).count()
        blocked = (db.query(Decision)
                   .filter(Decision.org_id == org_id, Decision.action == "BLOCK").count())
        held = (db.query(Decision)
                .filter(Decision.org_id == org_id, Decision.action == "HOLD").count())
        print(f"Done. {total:,} transactions in DB | {blocked} blocked | {held} held for review")
        return total
    finally:
        db.close()


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1800
    seed(n=n)

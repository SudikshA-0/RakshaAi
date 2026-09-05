"""Live transaction simulator.

Produces realistic raw transactions on demand — a steady stream of mostly
legitimate traffic with occasional organic fraud, plus scripted attack bursts
(card-testing, account-takeover, high-value stolen card) for the live demo.
The output feeds the exact same ingest pipeline the API uses.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Transaction

CATEGORIES = ["electronics", "fashion", "grocery", "food_delivery", "utilities",
              "travel", "gaming", "digital_goods", "gift_cards"]
FREEMAIL = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com"]
DISPOSABLE = ["mailinator.com", "tempmail.com", "guerrillamail.com"]
INTL = ["US", "GB", "AE", "SG", "NG", "RU"]
RISKY_BINS = ["411111", "444444", "512345", "601100", "355555"]
NORMAL_BINS = ["402100", "434000", "460000", "521000", "553000"]


def demo_now(db: Session | None = None, org_id: int | None = None) -> datetime:
    """Clock for live/simulated traffic, aligned with the latest stored txn.

    Seeded history uses dataset timestamps. If wall-clock time is within 24h of
    that history, use wall clock so 24h velocity still sees recent seed rows.
    If the seed window has drifted, continue from the latest timestamp so
    1h/24h velocity and ring detection stay meaningful in the demo.

    Scoped to ``org_id`` when given so each tenant's clock follows its own
    traffic rather than another merchant's.
    """
    wall = datetime.utcnow()
    if db is None:
        return wall
    stmt = select(func.max(Transaction.ts))
    if org_id is not None:
        stmt = stmt.where(Transaction.org_id == org_id)
    latest = db.execute(stmt).scalar()
    if latest is None:
        return wall
    if wall >= latest and (wall - latest) <= timedelta(hours=24):
        return wall
    if wall < latest:
        return latest + timedelta(seconds=random.randint(6, 25))
    return latest + timedelta(seconds=random.randint(6, 25))


def _returning_customer(db: Session, org_id: int) -> dict | None:
    """Sample a real seeded customer so returning-buyer history looks authentic.

    Restricted to ``org_id`` so one merchant's simulator never surfaces another
    tenant's customer/card/device data.
    """
    row = db.execute(
        select(Transaction)
        .where(Transaction.org_id == org_id,
               Transaction.is_fraud == 0, Transaction.fraud_pattern == "legit")
        .order_by(func.random()).limit(1)
    ).scalar_one_or_none()
    if row is None:
        return None
    return {
        "customer_id": row.customer_id, "card_hash": row.card_hash,
        "card_bin": row.card_bin, "card_type": row.card_type,
        "device_id": row.device_id, "ip": row.ip, "email": row.email,
        "account_age_days": row.account_age_days, "amount": row.amount,
    }


def random_transaction(db: Session, org_id: int) -> dict:
    roll = random.random()
    now = demo_now(db, org_id)

    if roll < 0.86:  # legitimate returning customer
        base = _returning_customer(db, org_id)
        if base is None:
            base = {"customer_id": f"CUST{random.randint(0,9999):05d}",
                    "card_hash": f"tok_{random.randint(0,9999)}",
                    "card_bin": random.choice(NORMAL_BINS), "card_type": "debit",
                    "device_id": f"dev_{random.randint(0,9999):05d}",
                    "ip": f"49.{random.randint(0,255)}.{random.randint(0,255)}.1",
                    "email": f"user{random.randint(0,9999)}@{random.choice(FREEMAIL)}",
                    "account_age_days": random.randint(30, 1500), "amount": 800}
        amount = max(50, base["amount"] * random.uniform(0.5, 1.8))
        cb = 1 if random.random() < 0.03 else 0
        return {**base, "amount": round(amount, 2),
                "category": random.choice(CATEGORIES),
                "channel": random.choice(["mobile", "mobile", "web", "pos"]),
                "billing_country": "IN", "shipping_country": "IN", "ts": now,
                "is_fraud": 0, "is_chargeback": cb,
                "fraud_pattern": "friendly_fraud" if cb else "legit"}

    # organic fraud
    kind = random.choice(["stolen_card", "account_takeover", "high_value"])
    if kind == "account_takeover":
        base = _returning_customer(db, org_id)
        if base:
            return {**base, "amount": round(base["amount"] * random.uniform(3, 7), 2),
                    "device_id": f"dev_new_{random.randint(0,99999):05d}",
                    "ip": f"103.{random.randint(0,255)}.{random.randint(0,255)}.9",
                    "category": random.choice(["electronics", "gift_cards", "travel"]),
                    "channel": "web", "billing_country": "IN",
                    "shipping_country": random.choice(INTL), "ts": now,
                    "is_fraud": 1, "is_chargeback": 1, "fraud_pattern": "account_takeover"}
    # stolen / high value
    return {"customer_id": f"guest_{random.randint(0,10**6)}",
            "card_hash": f"stolen_{random.randint(0,10**9)}",
            "card_bin": random.choice(RISKY_BINS + NORMAL_BINS),
            "card_type": random.choice(["credit", "prepaid"]),
            "device_id": f"dev_atk_{random.randint(0,99999):05d}",
            "ip": f"185.{random.randint(0,255)}.{random.randint(0,255)}.7",
            "email": f"buyer{random.randint(0,10**6)}@{random.choice(DISPOSABLE)}",
            "amount": round(random.uniform(15000, 90000), 2),
            "category": random.choice(["electronics", "jewellery", "gift_cards"]),
            "channel": random.choice(["web", "api"]),
            "billing_country": random.choice(INTL), "shipping_country": "IN",
            "account_age_days": random.randint(1, 20), "ts": now,
            "is_fraud": 1, "is_chargeback": 1, "fraud_pattern": "stolen_card"}


def attack_burst(kind: str = "card_testing", count: int = 14,
                db: Session | None = None, org_id: int | None = None) -> list[dict]:
    """A coordinated attack from a single device — the money-saved demo moment."""
    now = demo_now(db, org_id)
    dev = f"dev_atk_{random.randint(0,99999):05d}"
    ip = f"185.{random.randint(0,255)}.{random.randint(0,255)}.66"

    if kind == "high_value":
        out = []
        for i in range(count):
            ts = now - timedelta(seconds=(count - 1 - i) * 20)  # ~20s apart
            out.append({
                "customer_id": f"guest_{random.randint(0,10**6)}",
                "card_hash": f"stolen_{random.randint(0,10**9)}",
                "card_bin": random.choice(RISKY_BINS), "card_type": "prepaid",
                "device_id": dev, "ip": ip,
                "email": f"buyer{random.randint(0,10**6)}@{random.choice(DISPOSABLE)}",
                "amount": round(random.uniform(25000, 120000), 2),
                "category": "gift_cards", "channel": "api",
                "billing_country": random.choice(INTL), "shipping_country": "IN",
                "account_age_days": random.randint(1, 6), "ts": ts,
                "is_fraud": 1, "is_chargeback": 1, "fraud_pattern": "high_value"})
        return out

    if kind == "account_takeover":
        # Compromised returning account: same customer/card/email/age, new device
        # + IP, shipping mismatch, spend spike. Distinct from card-testing.
        victim = _returning_customer(db, org_id) if (db is not None and org_id is not None) else None
        if victim is None:
            victim = {
                "customer_id": f"CUST{random.randint(0, 9999):05d}",
                "card_hash": f"tok_{random.randint(0, 9999)}",
                "card_bin": random.choice(NORMAL_BINS),
                "card_type": "credit",
                "email": f"user{random.randint(0, 9999)}@{random.choice(FREEMAIL)}",
                "account_age_days": random.randint(180, 1500),
                "amount": 1200.0,
            }
        atk_dev = f"dev_ato_{random.randint(0, 99999):05d}"
        atk_ip = f"103.{random.randint(0, 255)}.{random.randint(0, 255)}.9"
        ship = random.choice(INTL)
        usual = float(victim.get("amount") or 1200)
        out = []
        for i in range(count):
            ts = now - timedelta(seconds=(count - 1 - i) * 40)  # slower than card-testing
            out.append({
                "customer_id": victim["customer_id"],
                "card_hash": victim["card_hash"],
                "card_bin": victim["card_bin"],
                "card_type": victim.get("card_type") or "credit",
                "email": victim["email"],
                "account_age_days": int(victim.get("account_age_days") or 400),
                "device_id": atk_dev,
                "ip": atk_ip,
                "amount": round(usual * random.uniform(3.5, 8.0), 2),
                "category": random.choice(["electronics", "gift_cards", "travel", "jewellery"]),
                "channel": "web",
                "billing_country": "IN",
                "shipping_country": ship,
                "ts": ts,
                "is_fraud": 1,
                "is_chargeback": 1,
                "fraud_pattern": "account_takeover",
            })
        return out

    # default: card-testing burst — one device hammering many stolen cards
    out = []
    for i in range(count):
        ts = now - timedelta(seconds=(count - 1 - i) * 12)  # rapid-fire, ~12s apart
        out.append({
            "customer_id": f"guest_{random.randint(0,10**6)}",
            "card_hash": f"stolen_{random.randint(0,10**9)}",
            "card_bin": random.choice(RISKY_BINS + NORMAL_BINS),
            "card_type": random.choice(["credit", "prepaid"]),
            "device_id": dev, "ip": ip,
            "email": f"tester{random.randint(0,10**6)}@{random.choice(DISPOSABLE)}",
            "amount": round(random.uniform(20, 200), 2),
            "category": random.choice(["digital_goods", "gift_cards", "gaming"]),
            "channel": "api", "billing_country": random.choice(["IN"] + INTL),
            "shipping_country": "IN", "account_age_days": random.randint(1, 15),
            "ts": ts, "is_fraud": 1, "is_chargeback": 1,
            "fraud_pattern": "card_testing"})
    return out

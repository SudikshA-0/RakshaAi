"""Synthetic transaction generator for RakshaAI.

We can't ship a real card dataset (Kaggle auth, PII), so we *simulate* one with
deliberately planted fraud patterns. This is honest — clearly synthetic — yet
rich enough that a real gradient-boosted model has genuine signal to learn:
card-testing bursts, stolen-card high-value anomalies, account takeover,
bust-out rings, and (for the chargeback head) friendly-fraud disputes.

Output: backend/data/transactions.csv  containing every FEATURE_COLUMN plus raw
display fields and the two ground-truth labels. The training script and the DB
seeder both read this file.
"""
from __future__ import annotations

import pathlib
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # backend/
from app.config import DATA_DIR, RANDOM_SEED
from app.ml.features import (FEATURE_COLUMNS, RISKY_BINS, build_features,
                            email_domain_class)

rng = np.random.default_rng(RANDOM_SEED)

N_CUSTOMERS = 900
N_LEGIT = 11000
DAYS = 35
NOW = datetime(2026, 9, 4, 12, 0, 0)
START = NOW - timedelta(days=DAYS)

CATEGORIES = ["electronics", "fashion", "grocery", "food_delivery", "utilities",
              "travel", "gaming", "digital_goods", "gift_cards", "education",
              "jewellery", "other"]
LEGIT_CHANNELS = ["mobile", "mobile", "web", "web", "pos"]
FREEMAIL = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "rediffmail.com"]
DISPOSABLE = ["mailinator.com", "tempmail.com", "guerrillamail.com", "trashmail.com"]
INTL = ["US", "GB", "AE", "SG", "NG", "RU", "CN"]
NORMAL_BINS = ["402100", "434000", "460000", "521000", "553000", "607400", "508500"]
ALL_BINS = NORMAL_BINS + list(RISKY_BINS)


def _rand_ts() -> datetime:
    """Legit transactions skew toward daytime."""
    day = rng.integers(0, DAYS)
    hour = int(np.clip(rng.normal(14, 4), 0, 23))
    minute = rng.integers(0, 60)
    return START + timedelta(days=int(day), hours=hour, minutes=int(minute))


def make_customers() -> list[dict]:
    customers = []
    for i in range(N_CUSTOMERS):
        base = float(np.exp(rng.normal(np.log(900), 0.7)))          # typical order value
        n_cards = int(rng.choice([1, 1, 2, 3]))
        cards = [{"card_hash": f"tok_{i}_{c}",
                  "card_bin": rng.choice(NORMAL_BINS),
                  "card_type": rng.choice(["credit", "debit", "debit", "prepaid"])}
                 for c in range(n_cards)]
        customers.append({
            "customer_id": f"CUST{i:05d}",
            "device_id": f"dev_{i:05d}",
            "ip": f"49.{rng.integers(0,256)}.{rng.integers(0,256)}.{rng.integers(0,256)}",
            "email": f"user{i}@{rng.choice(FREEMAIL)}",
            "cards": cards,
            "base_amount": base,
            "account_age_days": int(np.clip(rng.normal(500, 350), 3, 2000)),
            "fav_categories": list(rng.choice(CATEGORIES, size=3, replace=False)),
        })
    return customers


def _base_row(ts, cust, card, amount, category, channel, billing, shipping,
              device, ip, email, account_age, is_fraud, is_cb, pattern):
    return {
        "ts": ts, "customer_id": cust, "card_hash": card["card_hash"],
        "card_bin": card["card_bin"], "card_type": card["card_type"],
        "device_id": device, "ip": ip, "email": email,
        "email_domain": email.split("@")[-1], "amount": round(float(amount), 2),
        "category": category, "channel": channel, "billing_country": billing,
        "shipping_country": shipping, "account_age_days": int(account_age),
        "is_fraud": int(is_fraud), "is_chargeback": int(is_cb),
        "fraud_pattern": pattern,
    }


def generate_events(customers) -> list[dict]:
    events: list[dict] = []

    # ---- Legitimate baseline -------------------------------------------------
    # A slice of legit traffic deliberately *looks* risky (big-ticket buys,
    # travelling customers, fresh accounts) so the model faces real
    # false-positive pressure rather than a trivially separable problem.
    for _ in range(N_LEGIT):
        c = customers[rng.integers(0, len(customers))]
        card = c["cards"][rng.integers(0, len(c["cards"]))]
        amount = float(np.exp(rng.normal(np.log(c["base_amount"]), 0.55)))
        category = rng.choice(c["fav_categories"])
        billing = shipping = "IN"
        acct = c["account_age_days"]
        roll = rng.random()
        if roll < 0.05:            # legit big-ticket purchase
            amount *= rng.uniform(3, 8)
            category = rng.choice(["electronics", "travel", "jewellery"])
        elif roll < 0.09:          # legit international (NRI / traveller)
            billing = shipping = rng.choice(INTL)
            category = "travel"
        elif roll < 0.12:          # legit but brand-new account
            acct = int(rng.integers(0, 6))
        events.append(_base_row(
            _rand_ts(), c["customer_id"], card, amount, category,
            rng.choice(LEGIT_CHANNELS), billing, shipping, c["device_id"],
            c["ip"], c["email"], acct, 0, 0, "legit"))

    # ---- Card-testing bursts -------------------------------------------------
    for _ in range(70):
        stealth = rng.random() < 0.25          # low-and-slow variant, harder to catch
        fraud_dev = f"dev_atk_{rng.integers(0, 99999):05d}"
        fraud_ip = f"185.{rng.integers(0,256)}.{rng.integers(0,256)}.{rng.integers(0,256)}"
        t0 = START + timedelta(days=int(rng.integers(0, DAYS)),
                               hours=int(rng.integers(0, 24)),
                               minutes=int(rng.integers(0, 60)))
        n = int(rng.integers(3, 7)) if stealth else int(rng.integers(8, 26))
        for k in range(n):
            gap = rng.integers(120, 600) if stealth else rng.integers(5, 40)
            ts = t0 + timedelta(seconds=int(k * gap))
            card = {"card_hash": f"stolen_{rng.integers(0,10**9)}",
                    "card_bin": rng.choice(ALL_BINS),
                    "card_type": rng.choice(["credit", "prepaid"])}
            cb = 1 if rng.random() < 0.4 else 0
            events.append(_base_row(
                ts, f"guest_{rng.integers(0,10**6)}", card,
                float(rng.uniform(150, 900) if stealth else rng.uniform(20, 220)),
                rng.choice(["food_delivery", "fashion", "other"]) if stealth
                else rng.choice(["digital_goods", "gift_cards", "gaming"]),
                rng.choice(["web", "mobile"]) if stealth else rng.choice(["api", "web"]),
                "IN" if stealth else rng.choice(["IN"] + INTL), "IN",
                fraud_dev, fraud_ip,
                f"tester{rng.integers(0,10**6)}@"
                + (rng.choice(FREEMAIL) if stealth else rng.choice(DISPOSABLE)),
                int(rng.integers(1, 20)), 1, cb, "card_testing"))

    # ---- High-value stolen card ---------------------------------------------
    for _ in range(260):
        stealth = rng.random() < 0.30      # moderate, domestic, daytime → sneaky
        c = customers[rng.integers(0, len(customers))]
        ts = START + timedelta(
            days=int(rng.integers(0, DAYS)),
            hours=int(rng.integers(9, 21) if stealth else rng.choice([1, 2, 3, 4, 23])),
            minutes=int(rng.integers(0, 60)))
        card = {"card_hash": f"stolen_{rng.integers(0,10**9)}",
                "card_bin": rng.choice(ALL_BINS),
                "card_type": rng.choice(["credit", "prepaid"])}
        amount = float(c["base_amount"] * (rng.uniform(2, 4) if stealth
                                           else rng.uniform(8, 25)))
        events.append(_base_row(
            ts, c["customer_id"], card, amount,
            rng.choice(["electronics", "jewellery", "gift_cards", "travel"]),
            rng.choice(["web", "mobile"]) if stealth else rng.choice(["web", "api"]),
            "IN" if stealth else rng.choice(INTL), "IN",
            f"dev_atk_{rng.integers(0,99999):05d}",
            f"185.{rng.integers(0,256)}.{rng.integers(0,256)}.{rng.integers(0,256)}",
            f"buyer{rng.integers(0,10**6)}@"
            + (rng.choice(FREEMAIL) if stealth else rng.choice(DISPOSABLE + FREEMAIL)),
            int(rng.integers(1, 40)), 1, 1 if rng.random() < 0.85 else 0,
            "stolen_card"))

    # ---- Account takeover (existing customer, new device + shipping change) --
    for _ in range(160):
        stealth = rng.random() < 0.30      # ships domestically, smaller uplift
        c = customers[rng.integers(0, len(customers))]
        card = c["cards"][rng.integers(0, len(c["cards"]))]
        ts = START + timedelta(days=int(rng.integers(0, DAYS)),
                               hours=int(rng.integers(0, 24)),
                               minutes=int(rng.integers(0, 60)))
        amount = float(c["base_amount"] * (rng.uniform(1.8, 3) if stealth
                                           else rng.uniform(3, 7)))
        events.append(_base_row(
            ts, c["customer_id"], card, amount,
            rng.choice(["electronics", "gift_cards", "travel"]),
            rng.choice(["web", "mobile"]), "IN",
            "IN" if stealth else rng.choice(INTL),   # shipping change (or not)
            f"dev_new_{rng.integers(0,99999):05d}",
            f"103.{rng.integers(0,256)}.{rng.integers(0,256)}.{rng.integers(0,256)}",
            c["email"], c["account_age_days"], 1,
            1 if rng.random() < 0.7 else 0, "account_takeover"))

    # ---- Bust-out ring (one device, many fresh accounts) --------------------
    for _ in range(45):
        ring_dev = f"dev_ring_{rng.integers(0,99999):05d}"
        ring_ip = f"45.{rng.integers(0,256)}.{rng.integers(0,256)}.{rng.integers(0,256)}"
        day = int(rng.integers(0, DAYS))
        for k in range(int(rng.integers(6, 15))):
            ts = START + timedelta(days=day, hours=int(rng.integers(0, 24)),
                                   minutes=int(rng.integers(0, 60)))
            card = {"card_hash": f"ring_{rng.integers(0,10**9)}",
                    "card_bin": rng.choice(ALL_BINS),
                    "card_type": rng.choice(["credit", "prepaid", "debit"])}
            events.append(_base_row(
                ts, f"mule_{rng.integers(0,10**6)}", card,
                float(rng.uniform(500, 4000)),
                rng.choice(["electronics", "fashion", "gift_cards"]),
                rng.choice(["web", "mobile"]), "IN", "IN", ring_dev, ring_ip,
                f"acct{rng.integers(0,10**6)}@{rng.choice(FREEMAIL + DISPOSABLE)}",
                int(rng.integers(1, 10)), 1, 1 if rng.random() < 0.6 else 0, "ring"))

    # ---- Friendly fraud (chargeback only — legit-looking, later disputed) ----
    for _ in range(320):
        c = customers[rng.integers(0, len(customers))]
        card = c["cards"][rng.integers(0, len(c["cards"]))]
        amount = float(c["base_amount"] * rng.uniform(2.5, 6))
        events.append(_base_row(
            _rand_ts(), c["customer_id"], card, amount,
            rng.choice(["electronics", "travel", "digital_goods", "gaming"]),
            rng.choice(["web", "mobile"]), "IN", "IN", c["device_id"], c["ip"],
            c["email"], c["account_age_days"], 0, 1, "friendly_fraud"))

    # ---- Label noise (realism: no dataset is perfectly labelled) -------------
    for e in events:
        if e["fraud_pattern"] == "legit" and rng.random() < 0.008:
            e["is_fraud"] = 1  # a few mislabelled / truly sneaky ones
    return events


def compute_velocity_features(events: list[dict]) -> pd.DataFrame:
    """Single forward pass in time order building the same velocity aggregates
    the live service computes from the DB. This mirrors serving semantics."""
    events.sort(key=lambda e: e["ts"])
    card_hist: dict[str, list] = {}   # card -> list[(ts, amount)]
    device_hist: dict[str, list] = {}  # device -> list[(ts, card, email)]
    ip_hist: dict[str, list] = {}      # ip -> list[ts]

    rows = []
    for i, e in enumerate(events):
        ts = e["ts"]
        h1 = ts - timedelta(hours=1)
        h24 = ts - timedelta(hours=24)

        ch = card_hist.get(e["card_hash"], [])
        card_count = len(ch)
        card_avg = float(np.mean([a for _, a in ch])) if ch else e["amount"]
        last_ts = ch[-1][0] if ch else None
        time_since = (ts - last_ts).total_seconds() / 3600.0 if last_ts else 720.0
        vc1 = sum(1 for t, _ in ch if t >= h1)
        vc24 = sum(1 for t, _ in ch if t >= h24)

        dh = device_hist.get(e["device_id"], [])
        vd1 = sum(1 for t, _, _ in dh if t >= h1)
        vd24 = sum(1 for t, _, _ in dh if t >= h24)
        cards_24 = {c for t, c, _ in dh if t >= h24} | {e["card_hash"]}
        emails_24 = {m for t, _, m in dh if t >= h24} | {e["email"]}

        ih = ip_hist.get(e["ip"], [])
        vip1 = sum(1 for t in ih if t >= h1)

        ctx = {
            "card_txn_count": card_count, "card_amount_avg": card_avg,
            "time_since_last_txn_hrs": time_since,
            "velocity_card_1h": vc1, "velocity_card_24h": vc24,
            "velocity_device_1h": vd1, "velocity_device_24h": vd24,
            "velocity_ip_1h": vip1,
            "distinct_cards_device_24h": len(cards_24),
            "distinct_emails_device_24h": len(emails_24),
        }
        feats = build_features(e, ctx)

        row = dict(e)
        row.update(feats)
        row["txn_ref"] = f"TXN{START.year}{i:07d}"
        rows.append(row)

        # update histories AFTER scoring (mirrors serving: insert post-decision)
        card_hist.setdefault(e["card_hash"], []).append((ts, e["amount"]))
        device_hist.setdefault(e["device_id"], []).append((ts, e["card_hash"], e["email"]))
        ip_hist.setdefault(e["ip"], []).append(ts)

    return pd.DataFrame(rows)


def main():
    print("Generating customers ...")
    customers = make_customers()
    print("Generating transaction events ...")
    events = generate_events(customers)
    print(f"  {len(events):,} raw events; computing velocity features ...")
    df = compute_velocity_features(events)

    fraud_rate = df["is_fraud"].mean()
    cb_rate = df["is_chargeback"].mean()
    out = DATA_DIR / "transactions.csv"
    df.to_csv(out, index=False)
    print(f"Saved {len(df):,} transactions -> {out}")
    print(f"  fraud rate       : {fraud_rate:.3%}")
    print(f"  chargeback rate  : {cb_rate:.3%}")
    print(f"  patterns         : {df['fraud_pattern'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()

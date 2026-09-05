"""Feature engineering — the single source of truth shared by the training
pipeline and the live scoring service.

Both paths call :func:`build_features` with (1) the raw transaction fields and
(2) a ``ctx`` dict of velocity / history aggregates. Keeping this in one place
is what prevents train/serve skew, the classic reason fraud models silently
degrade in production.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any

# --- Categorical risk lookups ---------------------------------------------
# Hand-tuned priors. The model learns the real weights; these just give the
# tree sensible, monotonic numeric inputs instead of raw strings.
CATEGORY_RISK = {
    "electronics": 0.75, "gift_cards": 0.95, "digital_goods": 0.70,
    "travel": 0.60, "gaming": 0.65, "fashion": 0.40, "grocery": 0.15,
    "food_delivery": 0.20, "utilities": 0.10, "education": 0.25,
    "jewellery": 0.85, "other": 0.45,
}
CHANNEL_RISK = {"web": 0.55, "mobile": 0.35, "api": 0.65, "pos": 0.10}
CARD_TYPE_RISK = {"prepaid": 0.85, "credit": 0.45, "debit": 0.30}
EMAIL_DOMAIN_RISK = {
    "disposable": 1.0, "freemail": 0.35, "corporate": 0.10, "unknown": 0.55,
}
# BINs (first 6 digits) flagged by prior chargeback history live in this set.
RISKY_BINS = {"411111", "444444", "512345", "601100", "355555"}

MERCHANT_COUNTRY = "IN"

# Canonical, ordered feature list. Order matters: the model is trained on this
# exact column order and the scorer feeds columns in the same order.
FEATURE_COLUMNS = [
    "amount",
    "log_amount",
    "hour",
    "day_of_week",
    "is_night",
    "category_risk",
    "channel_risk",
    "card_type_risk",
    "is_international",
    "billing_shipping_mismatch",
    "email_domain_risk",
    "bin_risk",
    "account_age_days",
    "is_new_account",
    "amount_to_avg_ratio",
    "card_txn_count",
    "velocity_card_1h",
    "velocity_card_24h",
    "velocity_device_1h",
    "velocity_device_24h",
    "velocity_ip_1h",
    "distinct_cards_device_24h",
    "distinct_emails_device_24h",
    "time_since_last_txn_hrs",
]

# Human-readable labels used when surfacing SHAP reason codes to merchants.
FEATURE_LABELS = {
    "amount": "Transaction amount",
    "log_amount": "Transaction amount",
    "hour": "Time of day",
    "day_of_week": "Day of week",
    "is_night": "Late-night transaction",
    "category_risk": "High-risk product category",
    "channel_risk": "Payment channel risk",
    "card_type_risk": "Card type (prepaid/credit)",
    "is_international": "International card",
    "billing_shipping_mismatch": "Billing/shipping country mismatch",
    "email_domain_risk": "Risky email domain",
    "bin_risk": "Card BIN flagged in dispute history",
    "account_age_days": "Account age",
    "is_new_account": "Newly created account",
    "amount_to_avg_ratio": "Amount vs customer's usual spend",
    "card_txn_count": "Card transaction history",
    "velocity_card_1h": "Card used repeatedly in last hour",
    "velocity_card_24h": "Card velocity (24h)",
    "velocity_device_1h": "Device velocity (1h)",
    "velocity_device_24h": "Device velocity (24h)",
    "velocity_ip_1h": "IP address velocity (1h)",
    "distinct_cards_device_24h": "Many cards from one device (card-testing signal)",
    "distinct_emails_device_24h": "Many accounts from one device (ring signal)",
    "time_since_last_txn_hrs": "Time since card's previous transaction",
}


def _to_dt(ts: Any) -> datetime:
    if isinstance(ts, datetime):
        return ts
    return datetime.fromisoformat(str(ts))


def email_domain_class(domain: str) -> str:
    """Bucket an email domain into a risk class."""
    domain = (domain or "").lower()
    disposable = {"mailinator.com", "tempmail.com", "guerrillamail.com",
                  "10minutemail.com", "throwaway.email", "trashmail.com"}
    freemail = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com",
                "proton.me", "rediffmail.com"}
    if domain in disposable:
        return "disposable"
    if domain in freemail:
        return "freemail"
    if domain.endswith((".edu", ".gov")) or "corp" in domain:
        return "corporate"
    if not domain:
        return "unknown"
    return "corporate" if "." in domain else "unknown"


def build_features(txn: dict, ctx: dict) -> dict:
    """Turn one raw transaction + its velocity context into the model's
    numeric feature dict.

    Parameters
    ----------
    txn : dict
        Raw transaction fields (amount, ts, category, channel, card_type,
        card_bin, email_domain, billing_country, shipping_country,
        account_age_days).
    ctx : dict
        Velocity / history aggregates computed either offline (training) or
        from the DB (serving). Missing keys default to a "no history" value.
    """
    dt = _to_dt(txn["ts"])
    amount = float(txn["amount"])
    hour = dt.hour

    card_avg = float(ctx.get("card_amount_avg") or amount)
    card_avg = card_avg if card_avg > 0 else amount
    domain_class = email_domain_class(txn.get("email_domain", ""))

    billing = (txn.get("billing_country") or MERCHANT_COUNTRY).upper()
    shipping = (txn.get("shipping_country") or billing).upper()

    feats = {
        "amount": amount,
        "log_amount": math.log1p(amount),
        "hour": float(hour),
        "day_of_week": float(dt.weekday()),
        "is_night": 1.0 if hour < 6 else 0.0,
        "category_risk": CATEGORY_RISK.get(txn.get("category", "other"), 0.45),
        "channel_risk": CHANNEL_RISK.get(txn.get("channel", "web"), 0.5),
        "card_type_risk": CARD_TYPE_RISK.get(txn.get("card_type", "credit"), 0.45),
        "is_international": 1.0 if billing != MERCHANT_COUNTRY else 0.0,
        "billing_shipping_mismatch": 1.0 if billing != shipping else 0.0,
        "email_domain_risk": EMAIL_DOMAIN_RISK.get(domain_class, 0.55),
        "bin_risk": 1.0 if str(txn.get("card_bin", ""))[:6] in RISKY_BINS else 0.0,
        "account_age_days": float(txn.get("account_age_days", 365)),
        "is_new_account": 1.0 if float(txn.get("account_age_days", 365)) < 7 else 0.0,
        "amount_to_avg_ratio": min(amount / card_avg, 50.0),
        "card_txn_count": float(ctx.get("card_txn_count", 0)),
        "velocity_card_1h": float(ctx.get("velocity_card_1h", 0)),
        "velocity_card_24h": float(ctx.get("velocity_card_24h", 0)),
        "velocity_device_1h": float(ctx.get("velocity_device_1h", 0)),
        "velocity_device_24h": float(ctx.get("velocity_device_24h", 0)),
        "velocity_ip_1h": float(ctx.get("velocity_ip_1h", 0)),
        "distinct_cards_device_24h": float(ctx.get("distinct_cards_device_24h", 1)),
        "distinct_emails_device_24h": float(ctx.get("distinct_emails_device_24h", 1)),
        "time_since_last_txn_hrs": min(float(ctx.get("time_since_last_txn_hrs", 720.0)), 720.0),
    }
    return feats


def feature_vector(txn: dict, ctx: dict) -> list[float]:
    """Ordered feature values for model input."""
    feats = build_features(txn, ctx)
    return [feats[c] for c in FEATURE_COLUMNS]

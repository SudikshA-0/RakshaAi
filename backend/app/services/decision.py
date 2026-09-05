"""Action / decision engine — the business layer on top of the ML scores.

Blends the fraud & chargeback probabilities into a single risk score, applies
the merchant's risk-appetite-adjusted thresholds, layers a coordinated-abuse
(ring) override, and estimates the rupee loss prevented. This is where model
output becomes a concrete, defensible action: ALLOW / STEP_UP / HOLD / BLOCK.
"""
from __future__ import annotations

from ..config import APPETITE_SHIFT, CHARGEBACK_FEE, LOSS_MITIGATION

_STATUS = {"BLOCK": "auto_blocked", "HOLD": "pending_review",
           "STEP_UP": "stepped_up", "ALLOW": "auto_allowed"}

# thresholds on the coordinated-abuse signals
RING_CARD_THRESHOLD = 5     # distinct cards from one device in 24h
RING_VELOCITY_THRESHOLD = 6  # transactions from one device in 1h
RING_BLOCK_CARDS = 8


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def effective_thresholds(policy: dict) -> dict:
    """Shift the base thresholds by the risk-appetite slider.

    appetite 0.5 = neutral (base). Higher appetite lowers thresholds → the
    system blocks more aggressively; lower appetite protects revenue.
    """
    shift = (policy["risk_appetite"] - 0.5) * 2 * APPETITE_SHIFT
    return {
        "block": _clamp(policy["block_threshold"] - shift),
        "review": _clamp(policy["review_threshold"] - shift),
        "challenge": _clamp(policy["challenge_threshold"] - shift),
    }


def decide(fraud_score: float, chargeback_score: float, ctx: dict,
           policy: dict, amount: float) -> dict:
    w = policy["chargeback_weight"]
    risk_score = (1 - w) * fraud_score + w * chargeback_score

    thr = effective_thresholds(policy)
    auto_block = policy["auto_block_enabled"]

    # --- coordinated-abuse (ring) detection ----------------------------------
    distinct_cards = int(ctx.get("distinct_cards_device_24h", 1))
    device_velocity = int(ctx.get("velocity_device_1h", 0))
    ring_flag = distinct_cards >= RING_CARD_THRESHOLD or device_velocity >= RING_VELOCITY_THRESHOLD
    ring_size = max(distinct_cards, device_velocity)

    # --- base action from thresholds -----------------------------------------
    if risk_score >= thr["block"] and auto_block:
        action = "BLOCK"
    elif risk_score >= thr["review"]:
        action = "HOLD"
    elif risk_score >= thr["challenge"]:
        action = "STEP_UP"
    else:
        action = "ALLOW"

    # --- ring override: never let a detected ring slip through ---------------
    if ring_flag:
        if distinct_cards >= RING_BLOCK_CARDS and auto_block:
            action = "BLOCK"
        elif action in ("ALLOW", "STEP_UP"):
            action = "HOLD"

    expected_loss = fraud_score * (amount + CHARGEBACK_FEE)
    expected_loss_prevented = LOSS_MITIGATION.get(action, 0.0) * expected_loss

    return {
        "risk_score": round(risk_score, 4),
        "action": action,
        "status": _STATUS[action],
        "thresholds": {k: round(v, 4) for k, v in thr.items()},
        "ring_flag": ring_flag,
        "ring_size": ring_size,
        "expected_loss": round(expected_loss, 2),
        "expected_loss_prevented": round(expected_loss_prevented, 2),
    }

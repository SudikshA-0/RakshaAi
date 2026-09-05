"""Central configuration for the RakshaAI backend.

Everything that a deployer might want to tune (paths, cost model, default
policy) lives here so the rest of the code never hard-codes magic numbers.
"""
from __future__ import annotations

import os
from pathlib import Path

# --- Paths -----------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent          # .../backend
APP_DIR = BACKEND_DIR / "app"
ARTIFACTS_DIR = APP_DIR / "ml" / "artifacts"                   # trained model + metrics
DATA_DIR = BACKEND_DIR / "data"                               # generated dataset
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND_DIR / ".env", override=True)
except ImportError:
    pass

DB_PATH = BACKEND_DIR / "rakshaai.db"
DATABASE_URL = os.getenv("RAKSHAAI_DATABASE_URL", f"sqlite:///{DB_PATH.as_posix()}")

# --- LLM / AI Analyst (Groq) -----------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_API_URL = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")

ENVIRONMENT = os.getenv("ENVIRONMENT", os.getenv("NODE_ENV", "development")).lower()

# --- Auth / multi-tenancy --------------------------------------------------
# Dashboard users authenticate with a Bearer JWT. In production, ALWAYS set
# RAKSHAAI_SECRET_KEY to a long random value; the dev fallback is not secret.
raw_secret = os.getenv("RAKSHAAI_SECRET_KEY", "")
if ENVIRONMENT in ("production", "prod") and (not raw_secret or raw_secret == "dev-insecure-secret-change-me-in-production"):
    raise RuntimeError("RAKSHAAI_SECRET_KEY environment variable must be set to a secure secret in production.")
SECRET_KEY = raw_secret or "dev-insecure-secret-change-me-in-production"
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("RAKSHAAI_TOKEN_EXPIRE_MIN", "1440"))  # 24h

# --- CORS ------------------------------------------------------------------
raw_cors = os.getenv("CORS_ORIGINS", "")
if raw_cors.strip():
    CORS_ORIGINS = [orig.strip() for orig in raw_cors.split(",") if orig.strip()]
else:
    CORS_ORIGINS = ["*"]

# Seeded demo tenant. All pre-existing (single-tenant) data is backfilled to
# this organization so local development data is preserved, not destroyed.
# NB: the email must be a real, non-reserved domain — strict email validation
# (correct for a real SaaS) rejects reserved TLDs like ".local".
DEMO_ORG_NAME = os.getenv("RAKSHAAI_DEMO_ORG", "Demo Merchant")
DEMO_EMAIL = os.getenv("RAKSHAAI_DEMO_EMAIL", "demo@rakshaai.io")
DEMO_PASSWORD = os.getenv("RAKSHAAI_DEMO_PASSWORD", "demo12345")

# The model version stamped onto every decision for auditability. Derived from
# the trained-model metadata at load time; this is the fallback label.
MODEL_VERSION_FALLBACK = "unknown"

# --- Business / merchant context ------------------------------------------
MERCHANT_COUNTRY = "IN"
CURRENCY = "INR"

# --- Cost model (rupees) ---------------------------------------------------
# Used both by the training pipeline (to pick a loss-minimising threshold) and
# by the live decision engine (to estimate money saved per blocked fraud).
CHARGEBACK_FEE = 1500.0        # flat penalty a merchant eats on every dispute
FALSE_POSITIVE_MARGIN = 0.18   # lost profit fraction when a good order is blocked
FALSE_POSITIVE_FRICTION = 40.0 # fixed friction cost (support, lost trust) per false block

# How much of the potential loss each action actually mitigates.
# Money Saved = (amount + CHARGEBACK_FEE) × mitigation, for actual fraud only.
LOSS_MITIGATION = {"BLOCK": 1.0, "HOLD": 1.0, "STEP_UP": 0.7, "ALLOW": 0.0}


def potential_loss(amount: float) -> float:
    return float(amount or 0.0) + CHARGEBACK_FEE


def prevented_loss(amount: float, action: str, is_fraud: int | bool) -> float:
    """Gross loss prevented. Only actual fraudulent transactions count."""
    if not is_fraud:
        return 0.0
    return LOSS_MITIGATION.get(action or "ALLOW", 0.0) * potential_loss(amount)

# --- Default risk policy ---------------------------------------------------
# risk_appetite in [0,1]: 0 = protect revenue (fewer blocks), 1 = block aggressively.
DEFAULT_POLICY = {
    "risk_appetite": 0.5,
    # base thresholds on the blended risk score; the appetite shifts them.
    "block_threshold": 0.82,
    "review_threshold": 0.55,
    "challenge_threshold": 0.35,
    "chargeback_weight": 0.35,   # how much chargeback score blends into risk
    "auto_block_enabled": True,
}

# blended-score threshold band width the appetite slider can move thresholds by
APPETITE_SHIFT = 0.18

# --- ML settings -----------------------------------------------------------
RANDOM_SEED = 42
TEST_FRACTION = 0.2            # temporal hold-out fraction

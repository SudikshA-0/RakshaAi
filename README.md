# RakshaAI — Merchant Risk Command Center

A defense-only AI risk platform that prevents merchant losses from **fraud, chargebacks, and abuse** in real time. Every transaction is scored by two gradient-boosted models, run through a cost-sensitive decision engine (ALLOW / STEP-UP / HOLD / BLOCK), explained with reason codes, and surfaced on a live command-center dashboard with a human-in-the-loop review queue.

> **Strictly defensive.** The system only *detects and blocks* malicious activity. It contains nothing offense-capable — no attack tooling, no evasion, no targeting. The "Simulate Attack" button generates synthetic hostile traffic **against our own engine** purely to demonstrate detection.

---

## What's inside

| Layer | Tech |
|-------|------|
| Frontend | Vite + React 18, Tailwind CSS, Recharts, framer-motion, lucide-react |
| Backend | FastAPI, SQLAlchemy 2.0, Pydantic v2 |
| ML | XGBoost (fraud + chargeback models), scikit-learn, SHAP-style reason codes, cost-sensitive threshold tuning |
| Database | SQLite by default (zero-config); swappable to Postgres via one env var |

### Core flow
```
transaction → fraud model + chargeback model → blended risk score
           → policy/threshold engine → decision (ALLOW/STEP_UP/HOLD/BLOCK)
           → reason codes + ring detection → database → live dashboard
                                                      → analyst review → feedback loop
```

---

## Prerequisites

- **Python 3.11+**
- **Node.js 18+** (tested on Node 22)

That's it. **No LLM accounts, payment providers, or external services are required.** The entire system runs locally and is fully self-contained.

---

## Quick start

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate    # Windows Git Bash
# source .venv/bin/activate      # macOS / Linux
pip install -r requirements.txt
```

Generate the synthetic dataset and train the two models (one-time; artifacts are committed but this regenerates them):

```bash
python -m ml_pipeline.generate_data
```
```bash
python -m ml_pipeline.train
```

Run the API (it auto-creates the SQLite DB, seeds it from the dataset on first boot, and warms the models into memory):

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The backend is now live at **http://127.0.0.1:8000** — health check at `/api/health`, interactive API docs at `/docs`.

### 2. Frontend

In a second terminal:

```bash
cd frontend
npm install
```
```bash
npm run dev
```

Open **http://localhost:5173**. The Vite dev server proxies all `/api/*` calls to the backend on port 8000, so no CORS or URL config is needed.

Sign in with the seeded demo merchant using `demo@rakshaai.io` / `demo12345`, or
create an isolated merchant organization from the sign-up screen.

---

## Merchant API (Phase 2)

Dashboard users can create sandbox (`rsk_test_…`) and live (`rsk_live_…`) keys
through the authenticated developer API. The raw secret is returned only by the
creation response; RakshaAI stores a one-way hash and supports revocation.

```bash
# Authenticate as a dashboard user, then create a sandbox key.
curl -X POST http://127.0.0.1:8000/api/developer/keys \
  -H "Authorization: Bearer <dashboard-jwt>" \
  -H "Content-Type: application/json" \
  -d '{"name":"Local integration","environment":"sandbox"}'

# Score a merchant transaction. The API key determines the organization;
# transaction history, policy, velocity and ring detection stay tenant-scoped.
curl -X POST http://127.0.0.1:8000/api/v1/risk/score \
  -H "X-API-Key: rsk_test_<secret>" \
  -H "Content-Type: application/json" \
  -d '{"amount":1234,"customer_id":"CUST_42","card_hash":"tok_42","device_id":"dev_42","email":"buyer@example.com"}'
```

The response includes a request ID, fraud and chargeback probabilities, blended
risk score, decision, reason codes, model version, and ring-risk signals. API
keys are intentionally separate from dashboard JWTs.

---

## Webhooks Integration

Merchants can configure tenant-scoped HTTPS webhooks via the Developer panel or `/api/developer/webhooks` endpoints to receive real-time decision events (`risk.decision.created`, `risk.transaction.blocked`, `risk.transaction.review`).

### Webhook Signature Verification
Each delivery includes HTTP headers:
- `X-RakshaAI-Signature`: Hex-encoded HMAC-SHA256 of the raw canonical payload body, signed with the webhook's secret.
- `X-RakshaAI-Event-Id`: Unique event identifier for idempotency.

To verify a webhook payload:
```python
import hmac, hashlib

expected_sig = hmac.new(signing_secret.encode("utf-8"), request_bytes, hashlib.sha256).hexdigest()
is_valid = hmac.compare_digest(expected_sig, request_headers["X-RakshaAI-Signature"])
```


---

## Using the dashboard

- **Command Center** — live KPIs (transactions scored, fraud blocked, net loss prevented, model precision), transaction-flow trend, decision mix, threat-pattern breakdown, top risk drivers, and a live transaction stream. Click **Start live feed** to stream synthetic traffic, or **Simulate Attack** to launch a card-testing ring or high-value bust-out against the engine and watch it get neutralized.
- **Live Transactions** — every scored transaction, filterable by decision, searchable by ref/customer/device/email, with a ring-only toggle. Click any row for a full explainability drawer (risk gauge, fraud & chargeback scores, reason codes, linked entities, ground-truth verdict).
- **Case Queue** — human-in-the-loop review. Confirm fraud or release as legit; every decision is written back as labeled training data (visible in the learning-loop counters).
- **Model Performance** — precision/recall/F1/AUC for both models, PR curves, confusion matrices, the cost-sensitive threshold-optimization curve (rupee loss minimized, not just accuracy), and global feature importance.
- **Risk Policy** — tune risk sensitivity and chargeback weight, toggle auto-block. Changes are persisted and applied to live scoring instantly (the effective decision thresholds shift in real time).

---

## Configuration (optional)

Everything works out of the box. These are the *only* knobs, all optional:

| Variable | Default | Purpose |
|----------|---------|---------|
| `RAKSHAAI_DATABASE_URL` | `sqlite:///backend/rakshaai.db` | Point at Postgres/MySQL instead of SQLite, e.g. `postgresql+psycopg://user:pass@host/db`. |
| `RAKSHAAI_SECRET_KEY` | development-only fallback | Required as a long random secret in production for dashboard JWT signing. |
| `RAKSHAAI_TOKEN_EXPIRE_MIN` | `1440` | Dashboard JWT lifetime in minutes. |

Business/cost tunables (chargeback fee, false-positive margin, default policy, ML seed/split) live in [`backend/app/config.py`](backend/app/config.py) and are editable without touching code elsewhere.

---

## Resetting / re-seeding

Delete `backend/rakshaai.db` and restart the backend — it will re-seed a fresh database from `backend/data/transactions.csv` on boot. To regenerate the underlying dataset and models entirely, re-run the two `ml_pipeline` commands above.

---

## Project layout

```
Project2/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI entrypoint (seeds + warms model on boot)
│   │   ├── config.py          # all tunables (paths, cost model, default policy)
│   │   ├── database.py        # SQLAlchemy engine/session
│   │   ├── models.py          # ORM tables
│   │   ├── schemas.py         # Pydantic request/response models
│   │   ├── routers/           # /api/transactions, /cases, /analytics, /policy, /simulate
│   │   ├── services/          # decision engine, pipeline, simulator, seeder
│   │   └── ml/                # scorer + trained artifacts (models, metrics, metadata)
│   ├── ml_pipeline/
│   │   ├── generate_data.py   # synthetic transaction generator
│   │   └── train.py           # trains fraud + chargeback models, writes metrics
│   ├── data/transactions.csv  # generated dataset
│   ├── requirements.txt
│   └── rakshaai.db            # SQLite (auto-created)
└── frontend/
    ├── src/
    │   ├── views/             # Dashboard, Transactions, Cases, ModelPerformance, Policy
    │   ├── components/        # sidebar, charts, primitives, transaction drawer, live feed
    │   └── lib/               # api client, formatters, theme
    ├── vite.config.js         # dev server + /api proxy to :8000
    └── package.json
```

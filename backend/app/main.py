"""RakshaAI backend entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import CORS_ORIGINS
from .database import SessionLocal, bootstrap_tenancy, init_db
from .models import Transaction
from .routers import ai_analyst, api_keys, analytics, auth, cases, policy, public_risk, simulate, transactions, webhooks
from .services.pipeline import get_policy_row



@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        demo_org = bootstrap_tenancy()   # demo merchant org + login, idempotent
        get_policy_row(db, demo_org.id)  # ensure the demo org's policy exists
        from .services.rag import seed_knowledge_docs
        seed_knowledge_docs(db)          # seed RAG platform knowledge docs
        count = (db.query(Transaction)
                 .filter(Transaction.org_id == demo_org.id).count())
    finally:
        db.close()

    if count == 0:
        # first boot on a fresh machine: seed the demo org + warm the model so
        # the dashboard has real data immediately.
        try:
            from .services.seed import seed
            print("No transactions found — seeding historical data ...")
            seed(org_id=demo_org.id, n=1500)
        except FileNotFoundError:
            print("WARNING: no dataset found. Run the ML pipeline first "
                  "(see README). Starting empty.")
    try:
        from .ml.scorer import get_scorer
        get_scorer()  # warm the model into memory
        print("Model loaded and ready.")
    except FileNotFoundError:
        print("WARNING: model artifacts missing. Train the model first.")
    yield


app = FastAPI(
    title="RakshaAI — Merchant Risk Command Center",
    description="Defense-only AI risk platform: real-time fraud + chargeback "
                "scoring, explainable decisions, and automated protective actions.",
    version="1.0.0",
    lifespan=lifespan,
)

# Bearer-token auth (Authorization header), so cookies/credentials are not used.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(api_keys.router)
app.include_router(webhooks.router)
app.include_router(public_risk.router)
app.include_router(transactions.router)
app.include_router(cases.router)
app.include_router(analytics.router)
app.include_router(policy.router)
app.include_router(simulate.router)
app.include_router(ai_analyst.router)



@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok", "service": "rakshaai"}

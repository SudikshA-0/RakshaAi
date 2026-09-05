"""SQLAlchemy engine, session factory and declarative base."""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
else:
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
        future=True,
    )
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency yielding a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_decisions() -> None:
    """Add evaluation-integrity columns on existing SQLite databases."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    alters = {
        "original_model_action": "ALTER TABLE decisions ADD COLUMN original_model_action VARCHAR(12)",
        "final_action": "ALTER TABLE decisions ADD COLUMN final_action VARCHAR(12)",
        "analyst_override": "ALTER TABLE decisions ADD COLUMN analyst_override BOOLEAN DEFAULT 0",
    }
    with engine.begin() as conn:
        existing = {row[1] for row in conn.execute(text("PRAGMA table_info(decisions)"))}
        if not existing:
            return
        for col, ddl in alters.items():
            if col not in existing:
                conn.execute(text(ddl))
        conn.execute(text(
            "UPDATE decisions SET original_model_action = action "
            "WHERE original_model_action IS NULL OR original_model_action = ''"
        ))
        conn.execute(text(
            "UPDATE decisions SET final_action = action "
            "WHERE final_action IS NULL OR final_action = ''"
        ))
        conn.execute(text(
            "UPDATE decisions SET analyst_override = 0 WHERE analyst_override IS NULL"
        ))


def _migrate_webhooks() -> None:
    """Add columns introduced after the first webhook tables were created."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    with engine.begin() as conn:
        hooks = {row[1] for row in conn.execute(text("PRAGMA table_info(webhooks)"))}
        if hooks and "description" not in hooks:
            conn.execute(text("ALTER TABLE webhooks ADD COLUMN description VARCHAR(240) DEFAULT ''"))
        deliveries = {row[1] for row in conn.execute(text("PRAGMA table_info(webhook_deliveries)"))}
        if deliveries and "txn_id" not in deliveries:
            conn.execute(text("ALTER TABLE webhook_deliveries ADD COLUMN txn_id INTEGER"))


def _migrate_tenancy() -> None:
    """Add multi-tenancy columns to a pre-existing single-tenant SQLite DB.

    On a fresh (e.g. Postgres) database ``create_all`` already builds these
    columns, so this only runs for the legacy SQLite dev database. Data backfill
    (assigning existing rows to the demo org) happens in ``bootstrap_tenancy``.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return
    adds = {
        "transactions": ["ALTER TABLE transactions ADD COLUMN org_id INTEGER"],
        "decisions": ["ALTER TABLE decisions ADD COLUMN org_id INTEGER",
                      "ALTER TABLE decisions ADD COLUMN model_version VARCHAR(40)"],
        "feedback": ["ALTER TABLE feedback ADD COLUMN org_id INTEGER"],
        "policy": ["ALTER TABLE policy ADD COLUMN org_id INTEGER"],
    }
    col_of = {
        "ALTER TABLE transactions ADD COLUMN org_id INTEGER": "org_id",
        "ALTER TABLE decisions ADD COLUMN org_id INTEGER": "org_id",
        "ALTER TABLE decisions ADD COLUMN model_version VARCHAR(40)": "model_version",
        "ALTER TABLE feedback ADD COLUMN org_id INTEGER": "org_id",
        "ALTER TABLE policy ADD COLUMN org_id INTEGER": "org_id",
    }
    with engine.begin() as conn:
        for table, ddls in adds.items():
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if not existing:
                continue  # table doesn't exist yet; create_all made it fresh
            for ddl in ddls:
                if col_of[ddl] not in existing:
                    conn.execute(text(ddl))


def bootstrap_tenancy():
    """Ensure the seeded demo tenant exists and backfill any orphaned rows.

    Idempotent: safe to call on every boot. Returns the demo Organization. All
    pre-existing single-tenant rows (transactions/decisions/feedback/policy) are
    assigned to this org so existing local data is preserved, never discarded.
    """
    from .config import DEMO_EMAIL, DEMO_ORG_NAME, DEMO_PASSWORD
    from .models import Organization, OrganizationMember, User
    from .security import hash_password

    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.name == DEMO_ORG_NAME).first()
        if org is None:
            org = Organization(name=DEMO_ORG_NAME)
            db.add(org)
            db.flush()

        user = db.query(User).filter(User.email == DEMO_EMAIL).first()
        if user is None:
            user = User(email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD),
                        name="Demo Owner")
            db.add(user)
            db.flush()

        member = (db.query(OrganizationMember)
                  .filter(OrganizationMember.org_id == org.id,
                          OrganizationMember.user_id == user.id).first())
        if member is None:
            db.add(OrganizationMember(org_id=org.id, user_id=user.id, role="owner"))

        # Backfill orphaned single-tenant rows onto the demo org.
        for table in ("transactions", "decisions", "feedback", "policy"):
            db.execute(text(f"UPDATE {table} SET org_id = :oid WHERE org_id IS NULL"),
                       {"oid": org.id})
        db.commit()
        db.refresh(org)
        return org
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (register mappers)
    Base.metadata.create_all(bind=engine)
    _migrate_decisions()
    _migrate_tenancy()
    _migrate_webhooks()
    bootstrap_tenancy()

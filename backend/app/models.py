"""ORM models: the durable state of the risk platform.

Ground-truth labels (``is_fraud`` / ``is_chargeback``) live on Transaction so
that live precision/recall and false-positive cost can be measured honestly
against what actually happened — they are never fed to the model at score time.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer,
                        String, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Organization(Base):
    """A merchant tenant. Every merchant-owned resource is scoped to one."""
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class OrganizationMember(Base):
    """Join table: which users belong to which orgs, and in what role."""
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_org_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="owner")  # owner|admin|analyst
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class APIKey(Base):
    """A merchant integration credential.

    Only a one-way hash of the secret is persisted.  ``key_prefix`` is safe to
    display in the dashboard so a merchant can identify a key without ever
    being able to retrieve it again.
    """
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    environment: Mapped[str] = mapped_column(String(12), default="sandbox")
    key_prefix: Mapped[str] = mapped_column(String(32), index=True)
    secret_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Webhook(Base):
    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(240), default="")
    url: Mapped[str] = mapped_column(String(2048))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # Fernet-encrypted signing secret; never returned by normal API responses.
    secret_encrypted: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    webhook_id: Mapped[int] = mapped_column(ForeignKey("webhooks.id"), index=True)
    txn_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"), nullable=True, index=True)
    event_id: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Tenant scope. Nullable at the DB level so the migration can add the column
    # to an existing single-tenant database and backfill it; always populated by
    # application code for new rows.
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"),
                                               index=True, nullable=True)
    txn_ref: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)

    customer_id: Mapped[str] = mapped_column(String(32), index=True)
    card_hash: Mapped[str] = mapped_column(String(32), index=True)
    card_bin: Mapped[str] = mapped_column(String(8))
    card_type: Mapped[str] = mapped_column(String(12))
    device_id: Mapped[str] = mapped_column(String(32), index=True)
    ip: Mapped[str] = mapped_column(String(40), index=True)
    email: Mapped[str] = mapped_column(String(120))
    email_domain: Mapped[str] = mapped_column(String(60))

    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(4), default="INR")
    category: Mapped[str] = mapped_column(String(24))
    channel: Mapped[str] = mapped_column(String(12))
    billing_country: Mapped[str] = mapped_column(String(4))
    shipping_country: Mapped[str] = mapped_column(String(4))
    account_age_days: Mapped[int] = mapped_column(Integer, default=365)

    # Ground truth — used only for evaluation dashboards, never for scoring.
    is_fraud: Mapped[int] = mapped_column(Integer, default=0)
    is_chargeback: Mapped[int] = mapped_column(Integer, default=0)
    fraud_pattern: Mapped[str] = mapped_column(String(24), default="legit")

    source: Mapped[str] = mapped_column(String(12), default="live")  # seed|live|attack
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    decision: Mapped["Decision"] = relationship(back_populates="transaction",
                                                uselist=False)


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"),
                                               index=True, nullable=True)
    txn_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), unique=True,
                                        index=True)

    fraud_score: Mapped[float] = mapped_column(Float)
    chargeback_score: Mapped[float] = mapped_column(Float)
    risk_score: Mapped[float] = mapped_column(Float, index=True)

    # Version of the risk model that produced these scores — audit trail.
    model_version: Mapped[str] = mapped_column(String(40), default="unknown")

    action: Mapped[str] = mapped_column(String(12), index=True)  # final/operational action
    original_model_action: Mapped[str] = mapped_column(String(12), index=True, default="ALLOW")
    final_action: Mapped[str] = mapped_column(String(12), default="ALLOW")
    analyst_override: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), index=True)

    threshold_block: Mapped[float] = mapped_column(Float)
    threshold_review: Mapped[float] = mapped_column(Float)
    threshold_challenge: Mapped[float] = mapped_column(Float)

    expected_loss: Mapped[float] = mapped_column(Float, default=0.0)
    expected_loss_prevented: Mapped[float] = mapped_column(Float, default=0.0)

    reason_codes: Mapped[list] = mapped_column(JSON, default=list)
    ring_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    ring_size: Mapped[int] = mapped_column(Integer, default=0)

    analyst_label: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(),
                                                index=True)

    transaction: Mapped["Transaction"] = relationship(back_populates="decision")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"),
                                               index=True, nullable=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id"), index=True)
    txn_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"))
    analyst_label: Mapped[int] = mapped_column(Integer)   # 1 = fraud, 0 = legit
    note: Mapped[str] = mapped_column(String(240), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Policy(Base):
    __tablename__ = "policy"

    id: Mapped[int] = mapped_column(primary_key=True)
    # One policy row per organization (was a global singleton pre-SaaS).
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"),
                                               unique=True, index=True, nullable=True)
    risk_appetite: Mapped[float] = mapped_column(Float, default=0.5)
    block_threshold: Mapped[float] = mapped_column(Float, default=0.82)
    review_threshold: Mapped[float] = mapped_column(Float, default=0.55)
    challenge_threshold: Mapped[float] = mapped_column(Float, default=0.35)
    chargeback_weight: Mapped[float] = mapped_column(Float, default=0.35)
    auto_block_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(),
                                                onupdate=func.now())


class AIEmbedding(Base):
    """Document chunk and vector embedding for RAG search.

    org_id is Nullable: NULL indicates global platform knowledge (accessible by all tenants),
    while an explicit org_id scopes the document to a specific merchant organization.
    """
    __tablename__ = "ai_embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=True)
    doc_type: Mapped[str] = mapped_column(String(48), index=True)
    title: Mapped[str] = mapped_column(String(240), default="")
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(String(4000))
    meta_data: Mapped[dict] = mapped_column(JSON, default=dict)
    vector: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AIConversation(Base):
    """A persistent multi-turn chat session belonging to a merchant organization."""
    __tablename__ = "ai_conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(200), default="New Conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    messages: Mapped[list["AIMessage"]] = relationship(
        "AIMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AIMessage.created_at.asc()",
    )


class AIMessage(Base):
    """A durable user or assistant turn within an AI conversation."""
    __tablename__ = "ai_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(String(10000))
    sources: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    conversation: Mapped["AIConversation"] = relationship("AIConversation", back_populates="messages")



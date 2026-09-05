"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import AnyHttpUrl, BaseModel, EmailStr, Field


# --- Auth / tenancy --------------------------------------------------------
class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    org_name: str = Field(min_length=2, max_length=120)
    name: str = Field(default="", max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class OrgOut(BaseModel):
    id: int
    name: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    name: str


class AuthOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    org: OrgOut


class APIKeyCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    environment: str = Field(default="sandbox", pattern="^(sandbox|live)$")


class APIKeyOut(BaseModel):
    id: int
    name: str
    environment: str
    key_prefix: str
    created_at: datetime | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class APIKeyCreatedOut(APIKeyOut):
    # Returned exactly once, immediately after creation. It is never stored.
    api_key: str


class WebhookCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    url: AnyHttpUrl
    description: str = Field(default="", max_length=240)


class WebhookUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    url: AnyHttpUrl | None = None
    enabled: bool | None = None
    description: str | None = Field(default=None, max_length=240)


class WebhookOut(BaseModel):
    id: int
    name: str
    description: str = ""
    url: str
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WebhookCreatedOut(WebhookOut):
    # Returned exactly once after create or rotate. Never stored in list views.
    signing_secret: str


class WebhookDeliveryOut(BaseModel):
    id: int
    webhook_id: int
    event_id: str
    event_type: str
    status: str
    attempts: int
    response_status: int | None = None
    last_error: str | None = None
    created_at: datetime | None = None
    delivered_at: datetime | None = None


class TransactionIn(BaseModel):
    """Raw transaction payload accepted by the ingestion endpoint. Most fields
    are optional so partners can send whatever they have; the scorer fills
    sensible defaults."""
    amount: float = Field(gt=0)
    customer_id: str
    card_hash: str
    card_bin: str = "400000"
    card_type: str = "credit"
    device_id: str
    ip: str = "0.0.0.0"
    email: str = "unknown@unknown"
    category: str = "other"
    channel: str = "web"
    billing_country: str = "IN"
    shipping_country: str = "IN"
    account_age_days: int = 365
    currency: str = "INR"
    ts: Optional[datetime] = None


class ReasonCode(BaseModel):
    feature: str
    label: str
    value: float
    impact: float          # signed SHAP contribution (log-odds)
    direction: str         # "increases" | "decreases"


class DecisionOut(BaseModel):
    action: str
    status: str
    fraud_score: float
    chargeback_score: float
    risk_score: float
    expected_loss: float
    expected_loss_prevented: float
    ring_flag: bool
    ring_size: int
    reason_codes: list[ReasonCode]
    thresholds: dict[str, float]
    latency_ms: float


class ScoreResponse(BaseModel):
    txn_ref: str
    decision: DecisionOut


class FeedbackIn(BaseModel):
    analyst_label: int = Field(ge=0, le=1)  # 1 = confirm fraud, 0 = legitimate
    note: str = ""


class PolicyUpdate(BaseModel):
    risk_appetite: Optional[float] = Field(default=None, ge=0, le=1)
    chargeback_weight: Optional[float] = Field(default=None, ge=0, le=1)
    auto_block_enabled: Optional[bool] = None


class AttackRequest(BaseModel):
    kind: str = "card_testing"     # card_testing | account_takeover | high_value
    count: int = Field(default=14, ge=3, le=40)


# --- RAG / AI Analyst Foundation ------------------------------------------
class RAGQueryIn(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    conversation_id: Optional[int] = None
    top_k: int = Field(default=5, ge=1, le=20)
    doc_type: Optional[str] = None


class RAGSearchResult(BaseModel):
    id: int
    title: str
    content: str
    doc_type: str
    chunk_index: int
    score: float
    meta_data: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class AIEmbeddingOut(BaseModel):
    id: int
    org_id: Optional[int] = None
    doc_type: str
    title: str
    chunk_index: int
    content: str
    meta_data: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class AIMessageOut(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    sources: list[dict] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class AIConversationSummaryOut(BaseModel):
    id: int
    org_id: int
    user_id: Optional[int] = None
    title: str
    message_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AIConversationDetailOut(BaseModel):
    id: int
    org_id: int
    user_id: Optional[int] = None
    title: str
    messages: list[AIMessageOut] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AIConversationCreateIn(BaseModel):
    title: Optional[str] = Field(default="New Conversation", max_length=200)


class AIConversationUpdateIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)



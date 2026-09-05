"""Tenant-scoped, signed outbound webhook delivery."""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime

from cryptography.fernet import Fernet
from sqlalchemy import select

from ..config import SECRET_KEY
from ..database import SessionLocal
from ..models import Decision, Transaction, Webhook, WebhookDelivery

RETRIES = (0, 0.2, 0.6)
TEST_EVENT = "webhook.test"
DECISION_EVENTS = (
    "risk.decision.created",
    "risk.transaction.blocked",
    "risk.transaction.review",
)


def _allow_private() -> bool:
    return os.getenv("RAKSHAAI_WEBHOOK_ALLOW_PRIVATE", "").lower() in {"1", "true", "yes"}


def _cipher() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest())
    return Fernet(key)


def new_secret() -> str:
    return "whsec_" + secrets.token_urlsafe(32)


def encrypt_secret(secret: str) -> str:
    return _cipher().encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _cipher().decrypt(token.encode()).decode()


def encode_payload(payload: dict) -> bytes:
    """Canonical JSON bytes used both for HMAC and the HTTP body."""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")


def sign_body(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def validate_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Webhook URL must be a plain http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError("Webhook URL must not contain credentials")
    host = parsed.hostname.lower().rstrip(".")
    if not _allow_private():
        blocked_hosts = {
            "localhost", "localhost.localdomain", "metadata.google.internal",
            "metadata.internal", "ip6-localhost", "ip6-loopback",
        }
        if host in blocked_hosts or host.endswith(".local") or host.endswith(".internal"):
            raise ValueError("Webhook URL may not target localhost or internal hosts")
        try:
            ip = ipaddress.ip_address(host)
            if not ip.is_global:
                raise ValueError("Webhook URL may not target a private network")
        except ValueError as exc:
            if "private network" in str(exc) or "localhost" in str(exc):
                raise
    return url


def _safe_host(url: str) -> None:
    if _allow_private():
        return
    host = urllib.parse.urlparse(url).hostname
    if not host:
        raise ValueError("Webhook URL has no host")
    for result in socket.getaddrinfo(host, None):
        addr = ipaddress.ip_address(result[4][0])
        if not addr.is_global:
            raise ValueError("Webhook URL resolves to a non-public address")


def event_types(decision: Decision) -> list[str]:
    result = ["risk.decision.created"]
    action = decision.original_model_action or decision.action
    if action == "BLOCK":
        result.append("risk.transaction.blocked")
    elif decision.status == "pending_review" or action == "HOLD":
        result.append("risk.transaction.review")
    return result


def event_payload(event_id: str, event_type: str, txn: Transaction, decision: Decision) -> dict:
    return {
        "event_id": event_id,
        "event_type": event_type,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "organization_id": txn.org_id,
        "transaction_id": txn.id,
        "transaction_reference": txn.txn_ref,
        "risk_score": decision.risk_score,
        "fraud_probability": decision.fraud_score,
        "chargeback_probability": decision.chargeback_score,
        "decision": decision.original_model_action or decision.action,
        "reason_codes": decision.reason_codes or [],
        "model_version": decision.model_version,
        "risk_signals": {"ring_flag": decision.ring_flag, "ring_size": decision.ring_size},
    }


def test_payload(event_id: str, org_id: int) -> dict:
    return {
        "event_id": event_id,
        "event_type": TEST_EVENT,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "organization_id": org_id,
        "test": True,
        "message": "RakshaAI webhook test event — no transaction was created",
    }


def prepare_decision_deliveries(db, txn: Transaction, decision: Decision) -> list[int]:
    """Create durable delivery records after the scoring commit; no network work here."""
    if txn.org_id is None:
        return []
    hooks = db.execute(
        select(Webhook).where(Webhook.org_id == txn.org_id, Webhook.enabled.is_(True))
    ).scalars().all()
    delivery_ids = []
    for hook in hooks:
        for kind in event_types(decision):
            record = WebhookDelivery(
                org_id=txn.org_id,
                webhook_id=hook.id,
                txn_id=txn.id,
                event_id="evt_" + uuid.uuid4().hex,
                event_type=kind,
                status="pending",
            )
            db.add(record)
            db.flush()
            delivery_ids.append(record.id)
    if delivery_ids:
        db.commit()
    return delivery_ids


def enqueue_decision_webhooks(db, txn: Transaction, decision: Decision, background_tasks=None) -> list[int]:
    """Persist deliveries then hand them to FastAPI BackgroundTasks (or run inline)."""
    ids = prepare_decision_deliveries(db, txn, decision)
    for delivery_id in ids:
        if background_tasks is not None:
            background_tasks.add_task(deliver, delivery_id)
        else:
            deliver(delivery_id)
    return ids


def prepare_test_delivery(db, hook: Webhook) -> int:
    record = WebhookDelivery(
        org_id=hook.org_id,
        webhook_id=hook.id,
        txn_id=None,
        event_id="evt_" + uuid.uuid4().hex,
        event_type=TEST_EVENT,
        status="pending",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record.id


def _post(url: str, body: bytes, headers: dict) -> int:
    _safe_host(url)
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status


def deliver(delivery_id: int) -> None:
    """Best-effort bounded retry worker, safe for FastAPI BackgroundTasks."""
    db = SessionLocal()
    try:
        delivery = db.get(WebhookDelivery, delivery_id)
        if delivery is None or delivery.status == "delivered":
            return
        hook = db.get(Webhook, delivery.webhook_id)
        if hook is None or not hook.enabled:
            delivery.status = "skipped"
            delivery.last_error = "Webhook disabled"
            db.commit()
            return
        if delivery.event_type == TEST_EVENT:
            payload = test_payload(delivery.event_id, delivery.org_id)
        else:
            txn = db.get(Transaction, delivery.txn_id) if delivery.txn_id else None
            decision = None
            if txn is not None:
                decision = db.execute(
                    select(Decision).where(Decision.txn_id == txn.id, Decision.org_id == delivery.org_id)
                ).scalar_one_or_none()
            if txn is None or decision is None:
                delivery.status = "failed"
                delivery.last_error = "Decision context unavailable"
                db.commit()
                return
            payload = event_payload(delivery.event_id, delivery.event_type, txn, decision)
        body = encode_payload(payload)
        signature = sign_body(decrypt_secret(hook.secret_encrypted), body)
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "RakshaAI-Webhooks/1.0",
            "X-RakshaAI-Signature": signature,
            "X-RakshaAI-Event-Id": delivery.event_id,
        }
        for attempt, delay in enumerate(RETRIES, 1):
            if delay:
                time.sleep(delay)
            delivery.attempts = attempt
            try:
                status = _post(hook.url, body, headers)
                delivery.response_status = status
                if 200 <= status < 300:
                    delivery.status = "delivered"
                    delivery.delivered_at = datetime.utcnow()
                    delivery.last_error = None
                    db.commit()
                    return
                delivery.last_error = f"HTTP {status}"
            except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
                delivery.last_error = str(exc)[:500]
            db.commit()
        delivery.status = "failed"
        db.commit()
    finally:
        db.close()

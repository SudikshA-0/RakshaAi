"""Dashboard-managed merchant webhooks."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_org
from ..models import Organization, Webhook, WebhookDelivery
from ..schemas import WebhookCreateIn, WebhookUpdateIn
from ..services import webhooks as svc

router = APIRouter(prefix="/api/developer/webhooks", tags=["developer"])


def _serialize(hook: Webhook) -> dict:
    return {
        "id": hook.id,
        "name": hook.name,
        "description": hook.description or "",
        "url": hook.url,
        "enabled": hook.enabled,
        "created_at": hook.created_at,
        "updated_at": hook.updated_at,
    }


def _serialize_delivery(row: WebhookDelivery) -> dict:
    return {
        "id": row.id,
        "webhook_id": row.webhook_id,
        "event_id": row.event_id,
        "event_type": row.event_type,
        "status": row.status,
        "attempts": row.attempts,
        "response_status": row.response_status,
        "last_error": row.last_error,
        "created_at": row.created_at,
        "delivered_at": row.delivered_at,
    }


def _hook_for_org(db: Session, org: Organization, webhook_id: int) -> Webhook:
    hook = db.execute(
        select(Webhook).where(Webhook.id == webhook_id, Webhook.org_id == org.id)
    ).scalar_one_or_none()
    if hook is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return hook


def _validated_url(url) -> str:
    try:
        return svc.validate_url(str(url))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def list_webhooks(db: Session = Depends(get_db),
                  org: Organization = Depends(get_current_org)):
    rows = db.execute(
        select(Webhook).where(Webhook.org_id == org.id).order_by(Webhook.id.desc())
    ).scalars().all()
    return {"webhooks": [_serialize(h) for h in rows]}


@router.post("", status_code=201)
def create_webhook(payload: WebhookCreateIn, db: Session = Depends(get_db),
                   org: Organization = Depends(get_current_org)):
    secret = svc.new_secret()
    hook = Webhook(
        org_id=org.id,
        name=payload.name.strip(),
        description=(payload.description or "").strip(),
        url=_validated_url(payload.url),
        enabled=True,
        secret_encrypted=svc.encrypt_secret(secret),
    )
    db.add(hook)
    db.commit()
    db.refresh(hook)
    return {**_serialize(hook), "signing_secret": secret}


@router.patch("/{webhook_id}")
def update_webhook(webhook_id: int, payload: WebhookUpdateIn,
                   db: Session = Depends(get_db),
                   org: Organization = Depends(get_current_org)):
    hook = _hook_for_org(db, org, webhook_id)
    data = payload.model_dump(exclude_unset=True)
    if "url" in data and data["url"] is not None:
        hook.url = _validated_url(data["url"])
        data.pop("url")
    for key, value in data.items():
        if value is not None:
            setattr(hook, key, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(hook)
    return _serialize(hook)


@router.post("/{webhook_id}/rotate-secret")
def rotate_secret(webhook_id: int, db: Session = Depends(get_db),
                  org: Organization = Depends(get_current_org)):
    hook = _hook_for_org(db, org, webhook_id)
    secret = svc.new_secret()
    hook.secret_encrypted = svc.encrypt_secret(secret)
    db.commit()
    db.refresh(hook)
    return {**_serialize(hook), "signing_secret": secret}


@router.post("/{webhook_id}/disable")
def disable_webhook(webhook_id: int, db: Session = Depends(get_db),
                    org: Organization = Depends(get_current_org)):
    hook = _hook_for_org(db, org, webhook_id)
    hook.enabled = False
    db.commit()
    db.refresh(hook)
    return _serialize(hook)


@router.delete("/{webhook_id}/disable")
def disable_webhook_delete(webhook_id: int, db: Session = Depends(get_db),
                           org: Organization = Depends(get_current_org)):
    return disable_webhook(webhook_id, db, org)


@router.delete("/{webhook_id}")
def delete_disable_webhook(webhook_id: int, db: Session = Depends(get_db),
                           org: Organization = Depends(get_current_org)):
    """Disable (do not destroy) so delivery history remains available."""
    return disable_webhook(webhook_id, db, org)


@router.post("/{webhook_id}/enable")
def enable_webhook(webhook_id: int, db: Session = Depends(get_db),
                   org: Organization = Depends(get_current_org)):
    hook = _hook_for_org(db, org, webhook_id)
    hook.enabled = True
    db.commit()
    db.refresh(hook)
    return _serialize(hook)


@router.get("/{webhook_id}/deliveries")
def list_deliveries(webhook_id: int, db: Session = Depends(get_db),
                    org: Organization = Depends(get_current_org),
                    limit: int = Query(50, ge=1, le=200)):
    _hook_for_org(db, org, webhook_id)
    rows = db.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_id == webhook_id,
               WebhookDelivery.org_id == org.id)
        .order_by(WebhookDelivery.id.desc())
        .limit(limit)
    ).scalars().all()
    return {"deliveries": [_serialize_delivery(r) for r in rows]}


@router.post("/{webhook_id}/test")
def send_test_event(webhook_id: int, background_tasks: BackgroundTasks,
                    db: Session = Depends(get_db),
                    org: Organization = Depends(get_current_org)):
    hook = _hook_for_org(db, org, webhook_id)
    if not hook.enabled:
        raise HTTPException(status_code=400, detail="Enable the webhook before sending a test event")
    delivery_id = svc.prepare_test_delivery(db, hook)
    background_tasks.add_task(svc.deliver, delivery_id)
    delivery = db.get(WebhookDelivery, delivery_id)
    return {"delivery": _serialize_delivery(delivery), "test": True}

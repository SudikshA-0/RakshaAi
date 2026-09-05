"""Dashboard-managed merchant API keys.

The raw credential is created with cryptographically secure randomness and is
shown once only.  Every later operation exposes metadata, never the secret.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_org
from ..models import APIKey, Organization
from ..schemas import APIKeyCreateIn

router = APIRouter(prefix="/api/developer/keys", tags=["developer"])


def _serialize(key: APIKey) -> dict:
    return {
        "id": key.id,
        "name": key.name,
        "environment": key.environment,
        "key_prefix": key.key_prefix,
        "created_at": key.created_at,
        "last_used_at": key.last_used_at,
        "revoked_at": key.revoked_at,
    }


@router.get("")
def list_keys(db: Session = Depends(get_db),
              org: Organization = Depends(get_current_org)):
    keys = db.execute(
        select(APIKey).where(APIKey.org_id == org.id).order_by(APIKey.id.desc())
    ).scalars().all()
    return {"keys": [_serialize(key) for key in keys]}


@router.post("", status_code=201)
def create_key(payload: APIKeyCreateIn, db: Session = Depends(get_db),
               org: Organization = Depends(get_current_org)):
    env_marker = "test" if payload.environment == "sandbox" else "live"
    secret = f"rsk_{env_marker}_{secrets.token_urlsafe(32)}"
    key = APIKey(
        org_id=org.id,
        name=payload.name.strip(),
        environment=payload.environment,
        key_prefix=secret[:18],
        secret_hash=hashlib.sha256(secret.encode("utf-8")).hexdigest(),
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return {**_serialize(key), "api_key": secret}


@router.post("/{key_id}/revoke")
def revoke_key(key_id: int, db: Session = Depends(get_db),
               org: Organization = Depends(get_current_org)):
    key = db.execute(
        select(APIKey).where(APIKey.id == key_id, APIKey.org_id == org.id)
    ).scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=404, detail="API key not found")
    if key.revoked_at is None:
        key.revoked_at = datetime.utcnow()
        db.commit()
        db.refresh(key)
    return _serialize(key)

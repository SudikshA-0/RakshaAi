"""FastAPI dependencies for authentication and tenant resolution.

Every merchant-scoped route depends on :func:`get_current_org`, which turns the
Bearer token into a concrete Organization *and* re-verifies membership against
the database — so a token can never grant access to an org the user was removed
from. Routers then scope their queries with the returned ``org.id``.
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import APIKey, Organization, OrganizationMember, User
from .security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def get_claims(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    claims = decode_access_token(creds.credentials)
    if not claims or "sub" not in claims:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return claims


def get_current_user(claims: dict = Depends(get_claims),
                     db: Session = Depends(get_db)) -> User:
    user = db.get(User, int(claims["sub"]))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_current_org(claims: dict = Depends(get_claims),
                    db: Session = Depends(get_db)) -> Organization:
    user_id = int(claims["sub"])
    org_id = int(claims.get("org_id") or 0)
    member = db.execute(
        select(OrganizationMember).where(
            OrganizationMember.org_id == org_id,
            OrganizationMember.user_id == user_id,
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=403, detail="No access to this organization")
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


def get_api_key(x_api_key: str | None = Header(default=None),
                db: Session = Depends(get_db)) -> APIKey:
    """Authenticate a public integration call and resolve its credential.

    This intentionally accepts only ``X-API-Key`` (not dashboard JWTs), so
    public integrations and the browser console retain separate credentials.
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key")
    key_hash = hashlib.sha256(x_api_key.encode("utf-8")).hexdigest()
    key = db.execute(
        select(APIKey).where(APIKey.secret_hash == key_hash,
                             APIKey.revoked_at.is_(None))
    ).scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")
    org = db.get(Organization, key.org_id)
    if org is None:
        raise HTTPException(status_code=401, detail="API key organization not found")
    key.last_used_at = datetime.utcnow()
    db.commit()
    return key

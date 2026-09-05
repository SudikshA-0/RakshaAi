"""Authentication endpoints: sign up (creates the merchant org), log in, and
the current-session lookup. Dashboard users authenticate with a Bearer JWT.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import DEFAULT_POLICY
from ..database import get_db
from ..dependencies import get_current_org, get_current_user
from ..models import Organization, OrganizationMember, Policy, User
from ..schemas import AuthOut, LoginIn, OrgOut, SignupIn, UserOut
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _auth_payload(user: User, org: Organization) -> dict:
    return {
        "access_token": create_access_token(user.id, org.id),
        "token_type": "bearer",
        "user": UserOut(id=user.id, email=user.email, name=user.name),
        "org": OrgOut(id=org.id, name=org.name),
    }


@router.post("/signup", response_model=AuthOut)
def signup(payload: SignupIn, db: Session = Depends(get_db)):
    existing = db.execute(
        select(User).where(User.email == payload.email.lower())
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    org = Organization(name=payload.org_name.strip())
    db.add(org)
    db.flush()

    user = User(email=payload.email.lower(),
                password_hash=hash_password(payload.password),
                name=payload.name.strip())
    db.add(user)
    db.flush()

    db.add(OrganizationMember(org_id=org.id, user_id=user.id, role="owner"))
    # Give the new merchant its own policy row up front.
    db.add(Policy(org_id=org.id, **DEFAULT_POLICY))
    db.commit()
    db.refresh(org)
    db.refresh(user)
    return _auth_payload(user, org)


@router.post("/login", response_model=AuthOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.execute(
        select(User).where(User.email == payload.email.lower())
    ).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    member = db.execute(
        select(OrganizationMember).where(OrganizationMember.user_id == user.id)
        .order_by(OrganizationMember.id.asc())
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=403, detail="This account is not linked to an organization")
    org = db.get(Organization, member.org_id)
    return _auth_payload(user, org)


@router.get("/me", response_model=AuthOut)
def me(user: User = Depends(get_current_user), org: Organization = Depends(get_current_org)):
    # Re-issues a token so an active session naturally slides its expiry.
    return _auth_payload(user, org)

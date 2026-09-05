"""Authentication primitives: password hashing and JWT access tokens.

Kept dependency-light on purpose — ``bcrypt`` for hashing (no passlib shim, so
no version-compat surprises) and ``PyJWT`` for stateless Bearer tokens. The
token carries the user id and their active organization id so tenant scoping
never needs a membership lookup on the hot path (membership is still verified
in the dependency layer as defense in depth).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM, SECRET_KEY


# --- Passwords -------------------------------------------------------------
def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --- JWT access tokens -----------------------------------------------------
def create_access_token(user_id: int, org_id: int,
                        expires_minutes: int | None = None) -> str:
    exp_min = ACCESS_TOKEN_EXPIRE_MINUTES if expires_minutes is None else expires_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "org_id": int(org_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=exp_min)).timestamp()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Return the decoded claims, or ``None`` if the token is invalid/expired."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None

"""Risk-policy endpoints — the merchant's risk-appetite dial and toggles."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_org
from ..models import Organization
from ..schemas import PolicyUpdate
from ..services.decision import effective_thresholds
from ..services.pipeline import get_policy_row, policy_to_dict

router = APIRouter(prefix="/api/policy", tags=["policy"])


def _payload(policy) -> dict:
    d = policy_to_dict(policy)
    d["effective_thresholds"] = effective_thresholds(d)
    d["updated_at"] = policy.updated_at.isoformat() if policy.updated_at else None
    return d


@router.get("")
def get_policy(db: Session = Depends(get_db),
               org: Organization = Depends(get_current_org)):
    return _payload(get_policy_row(db, org.id))


@router.put("")
def update_policy(payload: PolicyUpdate, db: Session = Depends(get_db),
                  org: Organization = Depends(get_current_org)):
    policy = get_policy_row(db, org.id)
    data = payload.model_dump(exclude_none=True)
    for k, v in data.items():
        setattr(policy, k, v)
    db.commit()
    db.refresh(policy)
    return _payload(policy)

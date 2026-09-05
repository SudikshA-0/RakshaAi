"""Protected API router for the RAG-powered AI Analyst and persistent multi-chat conversations."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_org, get_current_user
from ..models import Organization, User
from ..schemas import (
    AIConversationCreateIn,
    AIConversationDetailOut,
    AIConversationSummaryOut,
    AIConversationUpdateIn,
    RAGQueryIn,
)
from ..services.ai_analyst import (
    analyze_merchant_query,
    clear_conversation_messages,
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations,
    update_conversation_title,
)

router = APIRouter(prefix="/api/ai-analyst", tags=["ai-analyst"])


@router.get("/conversations", response_model=list[AIConversationSummaryOut])
def get_conversations(
    db: Session = Depends(get_db),
    org: Organization = Depends(get_current_org),
):
    """List all AI conversations for the authenticated merchant organization."""
    return list_conversations(db=db, org_id=org.id)


@router.post("/conversations", response_model=AIConversationDetailOut)
def create_new_conversation(
    payload: AIConversationCreateIn = AIConversationCreateIn(),
    db: Session = Depends(get_db),
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
):
    """Create a new chat conversation for the merchant organization."""
    conv = create_conversation(
        db=db,
        org_id=org.id,
        user_id=user.id,
        title=payload.title or "New Conversation",
    )
    return conv


@router.get("/conversations/{conversation_id}", response_model=AIConversationDetailOut)
def get_conversation_details(
    conversation_id: int,
    db: Session = Depends(get_db),
    org: Organization = Depends(get_current_org),
):
    """Fetch conversation details and its full message history."""
    conv = get_conversation(db=db, org_id=org.id, conv_id=conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.patch("/conversations/{conversation_id}", response_model=AIConversationDetailOut)
def rename_conversation(
    conversation_id: int,
    payload: AIConversationUpdateIn,
    db: Session = Depends(get_db),
    org: Organization = Depends(get_current_org),
):
    """Rename a conversation title."""
    conv = update_conversation_title(
        db=db,
        org_id=org.id,
        conv_id=conversation_id,
        title=payload.title,
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.delete("/conversations/{conversation_id}")
def remove_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    org: Organization = Depends(get_current_org),
):
    """Delete a conversation and its messages."""
    success = delete_conversation(db=db, org_id=org.id, conv_id=conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted", "id": conversation_id}


@router.post("/conversations/{conversation_id}/clear", response_model=AIConversationDetailOut)
def clear_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    org: Organization = Depends(get_current_org),
):
    """Clear all messages inside a specific conversation."""
    conv = clear_conversation_messages(db=db, org_id=org.id, conv_id=conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.post("/query")
def query_ai_analyst(
    payload: RAGQueryIn,
    db: Session = Depends(get_db),
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
):
    """Query the AI Analyst with RAG-grounded contextual reasoning for the authenticated merchant."""
    return analyze_merchant_query(
        db=db,
        org=org,
        query=payload.query,
        conversation_id=payload.conversation_id,
        user=user,
        top_k=payload.top_k,
        doc_type=payload.doc_type,
    )


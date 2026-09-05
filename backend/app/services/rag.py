"""RAG Foundation: Document chunking, vector embedding, and tenant-scoped similarity search."""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
import urllib.parse
from typing import Any, Sequence

import numpy as np
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from ..models import AIEmbedding

DEFAULT_EMBEDDING_DIM = 64


def chunk_text(text: str, chunk_size: int = 400, overlap: int = 50) -> list[str]:
    """Split input text into overlapping text chunks cleanly by words/paragraphs."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    chunks = []
    current_chunk = ""

    for p in paragraphs:
        if len(current_chunk) + len(p) + 1 <= chunk_size:
            current_chunk = f"{current_chunk}\n\n{p}".strip() if current_chunk else p
        else:
            if current_chunk:
                chunks.append(current_chunk)
            if len(p) > chunk_size:
                words = p.split()
                w_chunk = ""
                for w in words:
                    if len(w_chunk) + len(w) + 1 <= chunk_size:
                        w_chunk = f"{w_chunk} {w}".strip()
                    else:
                        if w_chunk:
                            chunks.append(w_chunk)
                        tail_len = min(overlap, len(w_chunk))
                        w_chunk = w_chunk[-tail_len:] + " " + w if tail_len > 0 else w
                if w_chunk:
                    current_chunk = w_chunk
                else:
                    current_chunk = ""
            else:
                current_chunk = p

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def _local_embedding(text: str, dim: int = DEFAULT_EMBEDDING_DIM) -> list[float]:
    """Deterministic, zero-dependency local text vectorizer normalized to unit L2 norm."""
    vec = np.zeros(dim, dtype=np.float32)
    words = re.findall(r'\b\w+\b', text.lower())
    if not words:
        return vec.tolist()

    for word in words:
        h = int(hashlib.md5(word.encode('utf-8')).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if ((h >> 8) & 1) == 1 else -1.0
        vec[idx] += sign

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return [round(float(v), 6) for v in vec]


def get_embedding(text: str, dim: int = DEFAULT_EMBEDDING_DIM) -> list[float]:
    """Generate vector embedding for input text.

    Supports configurable external provider via RAKSHAAI_EMBEDDING_API_URL or GEMINI_API_KEY environment variables;
    falls back seamlessly to zero-config local normalized feature hashing.
    """
    api_url = os.getenv("RAKSHAAI_EMBEDDING_API_URL")
    api_key = os.getenv("RAKSHAAI_EMBEDDING_API_KEY") or os.getenv("GEMINI_API_KEY")

    if api_url and api_key:
        try:
            req_data = json.dumps({"text": text}).encode("utf-8")
            req = urllib.request.Request(
                api_url,
                data=req_data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, dict) and "embedding" in data:
                    v = np.array(data["embedding"], dtype=np.float32)
                    norm = np.linalg.norm(v)
                    if norm > 0:
                        v = v / norm
                    return [round(float(x), 6) for x in v]
        except Exception:
            pass  # Fall back to local vectorizer if external API fails

    return _local_embedding(text, dim=dim)


def cosine_similarity(vec1: Sequence[float], vec2: Sequence[float]) -> float:
    """Calculate cosine similarity between two vector representations."""
    v1 = np.array(vec1, dtype=np.float32)
    v2 = np.array(vec2, dtype=np.float32)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    sim = float(np.dot(v1, v2) / (norm1 * norm2))
    return round(max(0.0, min(1.0, sim)), 5)


def index_document(
    db: Session,
    org_id: int | None,
    doc_type: str,
    title: str,
    text: str,
    meta_data: dict | None = None,
    chunk_size: int = 400,
    overlap: int = 50,
) -> list[AIEmbedding]:
    """Chunk, embed, and store document sections in the SQLite embeddings table."""
    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    records = []
    meta = meta_data or {}

    for idx, chunk in enumerate(chunks):
        vec = get_embedding(chunk)
        record = AIEmbedding(
            org_id=org_id,
            doc_type=doc_type,
            title=title,
            chunk_index=idx,
            content=chunk,
            meta_data=meta,
            vector=vec,
        )
        db.add(record)
        records.append(record)

    db.commit()
    for r in records:
        db.refresh(r)
    return records


def retrieve_context(
    db: Session,
    query: str,
    org_id: int,
    top_k: int = 5,
    doc_type: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve top-k relevant document chunks scoped strictly to the merchant organization (plus global docs)."""
    q_vec = get_embedding(query)

    stmt = select(AIEmbedding).where(
        or_(AIEmbedding.org_id == org_id, AIEmbedding.org_id.is_(None))
    )
    if doc_type:
        stmt = stmt.where(AIEmbedding.doc_type == doc_type)

    candidates = db.execute(stmt).scalars().all()
    if not candidates:
        return []

    scored = []
    for c in candidates:
        sim = cosine_similarity(q_vec, c.vector)
        scored.append({
            "id": c.id,
            "org_id": c.org_id,
            "title": c.title,
            "doc_type": c.doc_type,
            "chunk_index": c.chunk_index,
            "content": c.content,
            "score": sim,
            "meta_data": c.meta_data or {},
            "created_at": c.created_at,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


# --- Knowledge Docs Seeder -------------------------------------------------

RAKSHAAI_KNOWLEDGE_DOCS = [
    {
        "title": "RakshaAI Risk Scoring Engine Architecture",
        "doc_type": "knowledge_doc",
        "content": (
            "RakshaAI uses two ensemble gradient-boosted XGBoost models: a Fraud Probability Model "
            "and a Chargeback Probability Model. Scores are combined into a blended Risk Score (0.0 to 1.0). "
            "Decisions are made by evaluating thresholds: ALLOW (low risk), STEP_UP (2FA/OTP challenge), "
            "HOLD (manual review queue), and BLOCK (auto-rejection). Analyst resolutions update the decision's "
            "final_action while preserving original_model_action for honest model precision/recall evaluation."
        ),
        "meta_data": {"category": "architecture", "system": "risk_engine"},
    },
    {
        "title": "Cost-Sensitive Loss Optimization Matrix",
        "doc_type": "knowledge_doc",
        "content": (
            "RakshaAI optimizes decisions based on monetary rupee loss rather than raw accuracy. "
            "Every fraudulent transaction incurs potential loss equal to Amount + Rs. 1500 chargeback fee. "
            "BLOCK and HOLD actions mitigate 100% of loss. STEP_UP mitigates 70% of loss. ALLOW mitigates 0%. "
            "False positive blocks incur a margin penalty. The threshold tuner selects thresholds that maximize "
            "Net Loss Prevented."
        ),
        "meta_data": {"category": "cost_model", "system": "loss_mitigation"},
    },
    {
        "title": "Attack Pattern Typologies & Detection",
        "doc_type": "knowledge_doc",
        "content": (
            "Card Testing Attack: Rapid low-value transactions across multiple card BINs from velocity spikes. "
            "Account Takeover (ATO): Single device or IP operating across multiple user accounts in short time windows. "
            "High Value Bust-Out: Sudden high-amount luxury/gift-card purchases on young accounts with shipping mismatch. "
            "Ring Risk: Device ID or IP address linking multiple suspicious cards across customers."
        ),
        "meta_data": {"category": "threat_intelligence", "system": "ring_detection"},
    },
]


def seed_knowledge_docs(db: Session) -> int:
    """Seed default platform knowledge documents if none exist."""
    existing = db.execute(
        select(AIEmbedding).where(AIEmbedding.org_id.is_(None))
    ).scalars().first()
    if existing is not None:
        return 0

    count = 0
    for doc in RAKSHAAI_KNOWLEDGE_DOCS:
        records = index_document(
            db=db,
            org_id=None,
            doc_type=doc["doc_type"],
            title=doc["title"],
            text=doc["content"],
            meta_data=doc["meta_data"],
        )
        count += len(records)
    return count

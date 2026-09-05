"""AI Analyst Service: Grounded LLM provider orchestration, prompt safety, and tenant-isolated context analysis."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
import urllib.request
import urllib.parse
import urllib.error
from typing import Any

logger = logging.getLogger("rakshaai.ai_analyst")

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import prevented_loss
from ..models import AIConversation, AIMessage, Decision, Organization, Transaction, User
from .rag import retrieve_context

SYSTEM_INSTRUCTIONS = """You are RakshaAI Analyst, an authoritative AI risk & fraud advisor for merchant organization "{org_name}".

### Core Directives:
1. **Direct Answer First**: Always answer the user's question directly and clearly in the opening sentence.
2. **Factual Accuracy on Actual Implementation**:
   - Describe the ACTUAL RakshaAI implementation from the provided knowledge base with precision.
   - Do NOT use speculative phrases like "typically", "for example in other systems", "an illustrative formula might be", or "could use alternative architectures" when the actual implementation is established.
   - **Risk Scoring Architecture**: RakshaAI uses a dual XGBoost ensemble (Fraud Probability Model + Chargeback Probability Model).
   - **Blended Risk Score Formula**: `Risk Score = (1 - w) * Fraud Score + w * Chargeback Score`, where `w` is the configured `chargeback_weight` (default 0.35).
   - **Expected Loss Formula**: `Expected Loss = Fraud Score * (Amount + ₹1,500)` where ₹1,500 is the fixed chargeback dispute fee.
     - CRITICAL: Expected Loss is calculated using the **Fraud Score (fraud probability) alone**, NEVER the blended risk score.
   - **Decision Actions & Loss Mitigation**:
     - `ALLOW`: Low risk, 0% loss mitigation.
     - `STEP_UP`: Medium risk, 2FA / OTP step-up verification, 70% loss mitigation.
     - `HOLD`: High risk, queued for analyst manual review, 100% loss mitigation.
     - `BLOCK`: Critical risk, automated rejection, 100% loss mitigation.
   - **Threat Typologies**:
     - *Card Testing*: Rapid low-value transactions across multiple card BINs driven by velocity spikes.
     - *Account Takeover (ATO)*: Single device or IP operating across multiple distinct user accounts in short time windows.
     - *High-Value Bust-Out*: Sudden high-amount purchases on young accounts with billing/shipping address mismatch.
     - *Ring Risk*: Device ID or IP linking multiple suspicious cards or customers into a coordinated fraud network.
3. **No Threshold or Data Hallucination**:
   - Never invent configured threshold numbers, merchant policy cutoffs, transaction numbers, customer identities, or analytics statistics.
   - Thresholds are dynamically tuned per merchant policy; do not state fabricated numbers as active configuration.
   - When real platform tool data is provided, state the exact calculated figures from the tool without recalculating or altering them.
   - If providing an illustrative calculation, clearly label it as *(Hypothetical Example)*.
4. **Targeted Response Length**:
   - For standard or simple questions, keep the answer concise: target **~2 to 4 short paragraphs or bullet points**.
   - Only include structured Markdown tables, deep walkthroughs, or numerical examples when the user explicitly requests details, examples, or tables.
5. **Preserve Multi-Turn Context**:
   - Maintain conversational context across dialogue turns.
   - Avoid repeating lengthy foundational explanations that were already provided earlier in the conversation.
6. **Clean Markdown Formatting**:
   - Use standard Markdown (`###` headers, bullet lists, bold emphasis, inline code).
   - When generating tables, use valid GitHub Flavored Markdown (GFM) pipe syntax (`| Col 1 | Col 2 |`) with clear headers and separator rows (`| --- | --- |`) so columns are cleanly delineated.
7. **No Meta Leaks & Clean Tool Presentation**:
   - Never mention internal tool names (such as `get_money_saved`, `get_transaction`, or `tools`), "RAG", "retrieved chunks", "grounding documents", "system prompt", or internal implementation details.
   - Never expose internal merchant/org identifiers or developer labels (such as "student") unless it is the merchant's actual user-facing display name.
   - Present live database analytics and transaction records naturally and conversationally in clear business language."""


def _sanitize_text(text: str) -> str:
    """Redact any sensitive credential patterns or key hashes and normalize unicode artifacts."""
    if not text:
        return ""
    # Normalize unicode non-breaking hyphens and narrow spaces
    text = text.replace('\u2011', '-').replace('\u202f', ' ').replace('\u00a0', ' ')
    # Mask API key strings and secret tokens
    text = re.sub(r'gsk_[a-zA-Z0-9_\-]+', '[REDACTED_API_KEY]', text)
    text = re.sub(r'rsk_(sandbox|live|test)_[a-zA-Z0-9_\-]+', '[REDACTED_API_KEY]', text)
    text = re.sub(r'whsec_[a-zA-Z0-9_\-]+', '[REDACTED_WEBHOOK_SECRET]', text)
    text = re.sub(r'(secret_hash|password_hash|secret_encrypted)["\']?\s*:\s*["\']?[a-zA-Z0-9_\-\.\$\/]+', r'\1: [REDACTED]', text)
    return text


def _generate_title_from_query(query: str) -> str:
    """Generate a clean, readable title from the user query."""
    q = (query or "").strip().replace("\n", " ")
    q = re.sub(r'^(what is|how does|explain|tell me about|can you explain|why is)\s+', '', q, flags=re.IGNORECASE)
    q = q.strip()
    if not q:
        return "Risk Analysis"
    q = q[0].upper() + q[1:] if len(q) > 1 else q.upper()
    if len(q) > 55:
        q = q[:52].rstrip() + "..."
    return q


def _should_call_money_saved_tool(query: str) -> bool:
    """Detect if the user query is asking for real-time money saved or prevented loss data."""
    q = (query or "").lower()
    patterns = [
        r'\bmoney saved\b',
        r'\bsavings\b',
        r'\bhow much (money )?did we save\b',
        r'\bhow much (money )?have we saved\b',
        r'\bprevented loss\b',
        r'\bloss prevented\b',
        r'\bsaved today\b',
        r'\btoday.*saved\b',
        r'\btoday.*savings\b',
        r'\bamount saved\b',
        r'\bwhat are our savings\b',
        r'\bhow much was saved\b',
        r'\bget_money_saved\b',
    ]
    return any(re.search(p, q) for p in patterns)


def _extract_transaction_identifier(query: str) -> str | None:
    """Extract a transaction ID or reference (e.g. '123', '#456', 'TXN_A1_99') from query."""
    q = (query or "").strip()
    if not q:
        return None

    # 1. Explicit reference pattern: e.g., TXN_12345, TXN-ABCD-12, txn_live_abc
    m_ref = re.search(r'\b(TXN[_-][a-zA-Z0-9_\-]+)\b', q, re.IGNORECASE)
    if m_ref:
        return m_ref.group(1)

    # 2. Key phrase patterns: "transaction 123", "txn #123", "tx 123", "order 123", "transaction id 123", "txn_id 123"
    patterns = [
        r'\b(?:transaction|txn|tx|payment|order)\s*(?:id|ref|reference|#|number)?\s*[:#]?\s*([0-9]+)\b',
        r'\b(?:transaction|txn|tx|payment|order)\s*(?:id|ref|reference|#|number)\s*[:#]?\s*([a-zA-Z0-9_\-]+)\b',
        r'\b(?:status of|details of|why was|lookup|check|explain|investigate)\s+(?:transaction|txn|tx|payment|order)?\s*#?\s*([0-9]+)\b',
        r'\bget_transaction\s*[:#]?\s*([a-zA-Z0-9_\-]+)\b',
    ]
    for p in patterns:
        m = re.search(p, q, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if val.lower() not in (
                "data", "rules", "policy", "history", "count", "volume", "amount",
                "metrics", "rate", "analysis", "system", "context", "status", "today",
            ):
                return val
    return None


def get_money_saved(db: Session, org_id: int, date: datetime.date | None = None) -> dict[str, Any]:
    """Calculate today's (or specified date's) money saved using real tenant-scoped transaction data and prevented_loss()."""
    target_date = date or datetime.utcnow().date()
    rows = db.execute(
        select(Transaction.ts, Transaction.amount, Transaction.is_fraud,
               Decision.action, Decision.original_model_action, Decision.final_action, Decision.status)
        .join(Decision, Decision.txn_id == Transaction.id)
        .where(Transaction.org_id == org_id)
    ).all()

    today_rows = [r for r in rows if r.ts.date() == target_date]

    saved_today = sum(
        prevented_loss(r.amount, r.original_model_action or r.action or "ALLOW", r.is_fraud)
        for r in today_rows
    )

    total_txns_today = len(today_rows)
    fraud_txns_today = sum(1 for r in today_rows if r.is_fraud == 1)
    prevented_txns_today = sum(
        1 for r in today_rows
        if r.is_fraud == 1 and prevented_loss(r.amount, r.original_model_action or r.action or "ALLOW", r.is_fraud) > 0
    )
    actions_today = Counter((r.original_model_action or r.action or "ALLOW") for r in today_rows)

    return {
        "date": target_date.isoformat(),
        "money_saved": round(saved_today, 2),
        "currency": "INR",
        "total_transactions": total_txns_today,
        "fraud_transactions_detected": fraud_txns_today,
        "loss_mitigated_transactions": prevented_txns_today,
        "actions_breakdown": {
            "BLOCK": actions_today.get("BLOCK", 0),
            "HOLD": actions_today.get("HOLD", 0),
            "STEP_UP": actions_today.get("STEP_UP", 0),
            "ALLOW": actions_today.get("ALLOW", 0),
        },
    }


def get_transaction(db: Session, org_id: int, txn_identifier: str | int) -> dict[str, Any] | None:
    """Retrieve transaction and decision details strictly scoped to org_id by integer ID or txn_ref."""
    stmt = (
        select(Transaction, Decision)
        .join(Decision, Decision.txn_id == Transaction.id)
        .where(Transaction.org_id == org_id)
    )

    if isinstance(txn_identifier, int) or (isinstance(txn_identifier, str) and txn_identifier.isdigit()):
        int_id = int(txn_identifier)
        row = db.execute(stmt.where((Transaction.id == int_id) | (Transaction.txn_ref == str(txn_identifier)))).first()
    else:
        row = db.execute(stmt.where(Transaction.txn_ref == str(txn_identifier))).first()

    if not row:
        return None

    txn, decision = row[0], row[1]
    card_last4 = str(abs(hash(txn.card_hash)))[-4:] if txn.card_hash else "0000"

    return {
        "transaction_id": txn.id,
        "txn_ref": txn.txn_ref,
        "timestamp": txn.ts.isoformat() if txn.ts else None,
        "amount": round(txn.amount, 2),
        "currency": txn.currency,
        "fraud_score": round(decision.fraud_score, 4),
        "chargeback_score": round(decision.chargeback_score, 4),
        "risk_score": round(decision.risk_score, 4),
        "final_action": decision.final_action or decision.action,
        "original_model_action": decision.original_model_action or decision.action,
        "status": decision.status,
        "analyst_override": bool(decision.analyst_override),
        "reason_codes": decision.reason_codes or [],
        "ring_signals": {
            "ring_flag": bool(decision.ring_flag),
            "ring_size": decision.ring_size,
        },
        "customer_details": {
            "customer_id": txn.customer_id,
            "email": txn.email,
            "email_domain": txn.email_domain,
            "device_id": txn.device_id,
            "ip": txn.ip,
            "account_age_days": txn.account_age_days,
        },
        "payment_details": {
            "card_bin": txn.card_bin,
            "card_last4": card_last4,
            "card_type": txn.card_type,
            "category": txn.category,
            "channel": txn.channel,
            "billing_country": txn.billing_country,
            "shipping_country": txn.shipping_country,
        },
    }


def _get_groq_config() -> tuple[str, str, str]:
    """Retrieve Groq API key, model, and URL, dynamically checking backend/.env if not in memory."""
    backend_dir = Path(__file__).resolve().parents[2]
    env_file = backend_dir / ".env"
    env_exists = env_file.exists()

    key_from_dotenv = ""
    model_from_dotenv = ""
    url_from_dotenv = ""

    if env_exists:
        try:
            from dotenv import dotenv_values
            vals = dotenv_values(env_file)
            key_from_dotenv = (vals.get("GROQ_API_KEY") or "").strip()
            model_from_dotenv = (vals.get("GROQ_MODEL") or "").strip()
            url_from_dotenv = (vals.get("GROQ_API_URL") or "").strip()
        except Exception:
            pass

    key_from_env = (os.getenv("GROQ_API_KEY") or "").strip()
    model_from_env = (os.getenv("GROQ_MODEL") or "").strip()
    url_from_env = (os.getenv("GROQ_API_URL") or "").strip()

    logger.debug("Resolved BACKEND_DIR: %s", backend_dir)
    logger.debug(".env path exists: %s (%s)", env_exists, env_file)
    logger.debug("dotenv_values contains GROQ_API_KEY: %s (char count: %d)", bool(key_from_dotenv), len(key_from_dotenv))
    logger.debug("os.getenv('GROQ_API_KEY') populated: %s (char count: %d)", bool(key_from_env), len(key_from_env))

    key = key_from_env or key_from_dotenv
    model = model_from_env or model_from_dotenv or "llama-3.3-70b-versatile"
    url = url_from_env or url_from_dotenv or "https://api.groq.com/openai/v1/chat/completions"

    return key, model, url


def call_llm_provider(
    system_prompt: str,
    user_prompt: str,
    context_chunks: list[dict],
    history: list[dict] | None = None,
    tool_data: dict | None = None,
) -> str:
    """Send system, conversation history, and user prompts to the configured LLM provider.

    Supports:
    1. Groq OpenAI-compatible Chat Completions API via GROQ_API_KEY and GROQ_MODEL.
    2. Custom LLM endpoint via RAKSHAAI_LLM_API_URL / RAKSHAAI_LLM_API_KEY.
    3. Google Gemini API via GEMINI_API_KEY.
    4. Deterministic, grounded local response generator fallback (when no external API key is set or on failure).
    """
    groq_api_key, groq_model, groq_api_url = _get_groq_config()
    has_key = bool(groq_api_key)
    logger.debug("Groq Key Detected: %s | Model: %s", has_key, groq_model)

    # Build messages array including conversation history if provided
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for turn in history:
            role = turn.get("role")
            content = turn.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": _sanitize_text(content)})
    messages.append({"role": "user", "content": user_prompt})

    # 1. Groq OpenAI-compatible Chat Completions endpoint
    if groq_api_key:
        models_to_try = [groq_model]
        if groq_model not in ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"):
            models_to_try.extend(["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"])

        for current_model in models_to_try:
            logger.debug("Attempting Groq HTTP request to: %s (model: %s)", groq_api_url, current_model)
            try:
                payload = json.dumps({
                    "model": current_model,
                    "messages": messages,
                    "temperature": 0.2,
                }).encode("utf-8")
                req = urllib.request.Request(
                    groq_api_url,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {groq_api_key}",
                        "User-Agent": "groq-python/0.11.0",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    status_code = getattr(resp, "status", getattr(resp, "code", 200))
                    logger.debug("Groq HTTP Response Status: %s", status_code)
                    res_data = json.loads(resp.read().decode("utf-8"))
                    choices = res_data.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        content = msg.get("content")
                        if content:
                            return _sanitize_text(content.strip())
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")
                logger.debug("Groq HTTP Error Status: %s (%s) -> %s", e.code, e.reason, err_body[:100])
                if e.code == 404:
                    continue
                break
            except Exception as e:
                logger.debug("Groq Request Failed: %s (%s)", type(e).__name__, e)
                break

    # 2. External custom LLM API endpoint
    api_url = os.getenv("RAKSHAAI_LLM_API_URL")
    api_key = os.getenv("RAKSHAAI_LLM_API_KEY") or os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    if api_url and api_key:
        try:
            payload = json.dumps({
                "system": system_prompt,
                "prompt": user_prompt,
                "messages": messages,
            }).encode("utf-8")
            req = urllib.request.Request(
                api_url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                if isinstance(res_data, dict) and "answer" in res_data:
                    return _sanitize_text(res_data["answer"].strip())
                elif isinstance(res_data, dict) and "text" in res_data:
                    return _sanitize_text(res_data["text"].strip())
        except Exception:
            pass

    # 3. Gemini API endpoint fallback
    if api_key and not api_url:
        try:
            gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            gemini_contents = []
            for m in messages:
                gemini_contents.append({
                    "role": "user" if m["role"] in ("user", "system") else "model",
                    "parts": [{"text": m["content"]}],
                })
            payload = json.dumps({"contents": gemini_contents}).encode("utf-8")
            req = urllib.request.Request(
                gemini_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                candidates = res_data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        return _sanitize_text(parts[0]["text"].strip())
        except Exception:
            pass

    # 4. Deterministic local response generator fallback
    if tool_data:
        tool_type = tool_data.get("type")
        if tool_type == "money_saved" or "money_saved" in tool_data:
            d = tool_data.get("data", tool_data)
            saved_amt = d.get("money_saved", 0.0)
            mitigated = d.get("loss_mitigated_transactions", 0)
            fraud = d.get("fraud_transactions_detected", 0)
            total = d.get("total_transactions", 0)
            return (
                f"Today, you saved **₹{saved_amt:,.2f}** across {mitigated} loss-mitigated transactions "
                f"({fraud} fraudulent transactions detected out of {total} total transactions evaluated)."
            )
        elif tool_type == "transaction":
            t = tool_data.get("data", {})
            tid = t.get("transaction_id")
            amt = t.get("amount", 0.0)
            curr = t.get("currency", "INR")
            action = t.get("final_action", "ALLOW")
            fraud_score = t.get("fraud_score", 0.0)
            risk_score = t.get("risk_score", 0.0)
            reasons = t.get("reason_codes", [])
            reason_str = f" Reason codes: {', '.join(reasons)}." if reasons else ""
            ring_info = ""
            if t.get("ring_signals", {}).get("ring_flag"):
                ring_info = f" Coordinated ring risk signal detected (cluster size: {t['ring_signals']['ring_size']})."
            return (
                f"Transaction **#{tid}** ({curr} {amt:,.2f}) was evaluated with action **{action}** "
                f"(Risk Score: **{risk_score}**, Fraud Probability: **{fraud_score}**).{reason_str}{ring_info}"
            )
        elif tool_type == "transaction_not_found":
            ident = tool_data.get("identifier")
            return f"Transaction **{ident}** was not found in your organization's records."

    if not context_chunks:
        return "I don't have enough information in the system context to answer that."

    top_chunk = context_chunks[0]
    score = top_chunk.get("score", 0.0)

    if score < 0.05:
        return "I don't have enough information in the system context to answer that."

    title = top_chunk.get("title", "System Context")
    content = top_chunk.get("content", "")

    answer = f"Based on {title}: {content}"
    if len(context_chunks) > 1:
        sec = context_chunks[1]
        if sec.get("score", 0.0) >= 0.05:
            answer += f"\n\nAdditionally ({sec.get('title', 'Reference')}): {sec.get('content', '')}"

    return _sanitize_text(answer.strip())


# --- Conversation Management Helper Functions -----------------------------

def list_conversations(db: Session, org_id: int) -> list[dict[str, Any]]:
    """List all conversations for an organization with message counts, newest first."""
    convs = (
        db.query(AIConversation)
        .filter(AIConversation.org_id == org_id)
        .order_by(AIConversation.updated_at.desc(), AIConversation.id.desc())
        .all()
    )

    results = []
    for c in convs:
        results.append({
            "id": c.id,
            "org_id": c.org_id,
            "user_id": c.user_id,
            "title": c.title,
            "message_count": len(c.messages),
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        })
    return results


def get_conversation(db: Session, org_id: int, conv_id: int) -> AIConversation | None:
    """Retrieve a single conversation if it belongs to the given tenant."""
    return (
        db.query(AIConversation)
        .filter(AIConversation.id == conv_id, AIConversation.org_id == org_id)
        .first()
    )


def create_conversation(
    db: Session,
    org_id: int,
    user_id: int | None = None,
    title: str = "New Conversation",
) -> AIConversation:
    """Create a new conversation belonging to the organization."""
    conv = AIConversation(
        org_id=org_id,
        user_id=user_id,
        title=title or "New Conversation",
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def update_conversation_title(
    db: Session,
    org_id: int,
    conv_id: int,
    title: str,
) -> AIConversation | None:
    """Rename a conversation for the tenant."""
    conv = get_conversation(db, org_id, conv_id)
    if not conv:
        return None
    conv.title = (title or "").strip() or "Untitled Chat"
    conv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(conv)
    return conv


def delete_conversation(db: Session, org_id: int, conv_id: int) -> bool:
    """Delete a conversation and all its messages."""
    conv = get_conversation(db, org_id, conv_id)
    if not conv:
        return False
    db.delete(conv)
    db.commit()
    return True


def clear_conversation_messages(db: Session, org_id: int, conv_id: int) -> AIConversation | None:
    """Delete all messages inside a conversation."""
    conv = get_conversation(db, org_id, conv_id)
    if not conv:
        return None
    for msg in list(conv.messages):
        db.delete(msg)
    conv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(conv)
    return conv


def analyze_merchant_query(
    db: Session,
    org: Organization,
    query: str,
    conversation_id: int | None = None,
    user: User | None = None,
    top_k: int = 5,
    doc_type: str | None = None,
) -> dict[str, Any]:
    """Retrieve tenant-scoped context and generate a grounded AI Analyst response, persisting the session."""
    clean_query = _sanitize_text((query or "").strip())
    if not clean_query:
        return {
            "conversation_id": conversation_id,
            "query": "",
            "answer": "Please provide a valid risk query or question.",
            "sources": [],
            "retrieved_chunks": 0,
        }

    # 1. Resolve or create conversation
    conv: AIConversation | None = None
    if conversation_id is not None:
        conv = get_conversation(db=db, org_id=org.id, conv_id=conversation_id)

    if conv is None:
        title = _generate_title_from_query(clean_query)
        conv = create_conversation(
            db=db,
            org_id=org.id,
            user_id=user.id if user else None,
            title=title,
        )
    elif conv.title in ("New Conversation", "New Chat", "Untitled Chat", "") and len(conv.messages) == 0:
        conv.title = _generate_title_from_query(clean_query)

    # 2. Extract conversation history for multi-turn prompt context (up to last 10 messages)
    history = []
    if conv and conv.messages:
        for m in conv.messages[-10:]:
            history.append({
                "role": m.role,
                "content": m.content,
            })

    # 3. Check for real-data tools
    tool_data = None
    if _should_call_money_saved_tool(clean_query):
        saved_stats = get_money_saved(db=db, org_id=org.id)
        tool_data = {
            "type": "money_saved",
            "data": saved_stats,
        }
    else:
        txn_id = _extract_transaction_identifier(clean_query)
        if txn_id:
            txn_record = get_transaction(db=db, org_id=org.id, txn_identifier=txn_id)
            if txn_record:
                tool_data = {
                    "type": "transaction",
                    "data": txn_record,
                }
            else:
                tool_data = {
                    "type": "transaction_not_found",
                    "identifier": txn_id,
                }

    # 4. Retrieve tenant-isolated context chunks (org_id == org.id or org_id IS NULL)
    chunks = retrieve_context(db=db, query=clean_query, org_id=org.id, top_k=top_k, doc_type=doc_type)

    # If no relevant context is found and no tool was executed, enforce strict grounding fallback
    if not tool_data and (not chunks or max((c.get("score", 0.0) for c in chunks), default=0.0) < 0.05):
        answer = "I don't have enough information in the system context to answer that."
        sources: list[dict] = []
    else:
        # Sanitize and format context blocks
        context_str = ""
        if chunks:
            for idx, c in enumerate(chunks, 1):
                clean_content = _sanitize_text(c["content"])
                context_str += f"\n### Reference Document {idx}: {c['title']}\n{clean_content}\n"

        if tool_data and tool_data.get("type") == "money_saved":
            ms_data = tool_data["data"]
            tool_str = (
                f"\n### Today's Loss Prevention & Transaction Summary for {org.name or 'Merchant'}:\n"
                f"- Date: {ms_data['date']}\n"
                f"- Confirmed Money Saved Today: ₹{ms_data['money_saved']:,.2f} {ms_data['currency']}\n"
                f"- Total Transactions Evaluated Today: {ms_data['total_transactions']}\n"
                f"- Fraud Transactions Detected Today: {ms_data['fraud_transactions_detected']}\n"
                f"- Loss-Mitigated Fraud Transactions: {ms_data['loss_mitigated_transactions']}\n"
                f"- Enforcement Actions Breakdown: BLOCK={ms_data['actions_breakdown']['BLOCK']}, "
                f"HOLD={ms_data['actions_breakdown']['HOLD']}, "
                f"STEP_UP={ms_data['actions_breakdown']['STEP_UP']}, "
                f"ALLOW={ms_data['actions_breakdown']['ALLOW']}\n\n"
                f"**CRITICAL PRESENTATION INSTRUCTIONS**:\n"
                f"1. Present the returned database values naturally and conversationally (e.g. 'Today, you saved ₹{ms_data['money_saved']:,.2f} across {ms_data['loss_mitigated_transactions']} transactions.').\n"
                f"2. Never mention internal tool names (such as 'get_money_saved', 'get_transaction', or 'tools'), 'RAG', 'system prompts', or implementation details.\n"
                f"3. Never expose internal merchant/org identifiers or developer labels (such as 'student') unless it is the merchant's actual user-facing display name.\n"
                f"4. State the exact money saved figure of ₹{ms_data['money_saved']:,.2f} INR without modifying or recalculating it."
            )
            context_str = f"{tool_str}\n{context_str}"

        elif tool_data and tool_data.get("type") == "transaction":
            t = tool_data["data"]
            reasons_text = ", ".join(t["reason_codes"]) if t["reason_codes"] else "None recorded"
            tool_str = (
                f"\n### Transaction Record #{t['transaction_id']} ({t['txn_ref']}) for {org.name or 'Merchant'}:\n"
                f"- Amount: ₹{t['amount']:,.2f} {t['currency']}\n"
                f"- Timestamp: {t['timestamp']}\n"
                f"- Fraud Score (Probability): {t['fraud_score']}\n"
                f"- Chargeback Score (Probability): {t['chargeback_score']}\n"
                f"- Blended Risk Score: {t['risk_score']}\n"
                f"- Final Action: {t['final_action']} (Original Model Action: {t['original_model_action']}, Status: {t['status']})\n"
                f"- Reason Codes / Triggered Signals: {reasons_text}\n"
                f"- Ring Signals: Ring Flag={t['ring_signals']['ring_flag']}, Ring Size={t['ring_signals']['ring_size']}\n"
                f"- Customer & Device: Customer ID={t['customer_details']['customer_id']}, Email={t['customer_details']['email']}, IP={t['customer_details']['ip']}, Device ID={t['customer_details']['device_id']}, Account Age={t['customer_details']['account_age_days']} days\n"
                f"- Payment Details: Card BIN={t['payment_details']['card_bin']}, Last 4={t['payment_details']['card_last4']}, Type={t['payment_details']['card_type']}, Category={t['payment_details']['category']}, Channel={t['payment_details']['channel']}, Billing Country={t['payment_details']['billing_country']}, Shipping Country={t['payment_details']['shipping_country']}\n\n"
                f"**CRITICAL PRESENTATION INSTRUCTIONS**:\n"
                f"1. Explain the transaction decision outcome directly using the real returned scores, reason codes, and signals.\n"
                f"2. Never invent missing reasons, missing signals, or unrecorded data.\n"
                f"3. Never mention internal tool names (such as 'get_transaction', 'get_money_saved', or 'tools'), 'RAG', 'system prompts', or implementation details.\n"
                f"4. Never expose internal merchant/org identifiers or developer labels.\n"
                f"5. Present the response naturally, clearly, and concisely in Markdown."
            )
            context_str = f"{tool_str}\n{context_str}"

        elif tool_data and tool_data.get("type") == "transaction_not_found":
            ident = tool_data["identifier"]
            tool_str = (
                f"\n### Transaction Search Result:\n"
                f"Transaction '{ident}' was not found in {org.name or 'Merchant'}'s records.\n"
                f"State clearly and politely that this transaction does not exist or cannot be found in the organization's records."
            )
            context_str = f"{tool_str}\n{context_str}"

        # Construct system prompt with ChatGPT-class directives & grounding
        system_prompt = SYSTEM_INSTRUCTIONS.format(org_name=org.name or "Merchant")
        system_prompt += f"\n\n### Reference Knowledge Base:\n{context_str}"

        # Call LLM Provider (or local fallback) with conversational history and tool data
        answer = call_llm_provider(
            system_prompt=system_prompt,
            user_prompt=clean_query,
            context_chunks=chunks,
            history=history,
            tool_data=tool_data,
        )

        sources = [
            {
                "id": c["id"],
                "title": c["title"],
                "doc_type": c["doc_type"],
                "chunk_index": c["chunk_index"],
                "score": c["score"],
            }
            for c in chunks
        ]
        if tool_data and tool_data.get("type") == "money_saved":
            sources.insert(0, {
                "id": 0,
                "title": "Real-Time Risk Analytics",
                "doc_type": "real_time_tool",
                "chunk_index": 0,
                "score": 1.0,
            })
        elif tool_data and tool_data.get("type") == "transaction":
            t = tool_data["data"]
            sources.insert(0, {
                "id": t["transaction_id"],
                "title": f"Transaction #{t['transaction_id']}",
                "doc_type": "transaction_record",
                "chunk_index": 0,
                "score": 1.0,
            })

    # 5. Persist user message and assistant response
    user_msg = AIMessage(
        conversation_id=conv.id,
        role="user",
        content=clean_query,
        sources=[],
    )
    bot_msg = AIMessage(
        conversation_id=conv.id,
        role="assistant",
        content=answer,
        sources=sources,
    )
    db.add(user_msg)
    db.add(bot_msg)
    conv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(conv)

    return {
        "conversation_id": conv.id,
        "query": clean_query,
        "answer": answer,
        "sources": sources,
        "retrieved_chunks": len(chunks) if chunks else 0,
    }



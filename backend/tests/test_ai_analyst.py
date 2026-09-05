"""Tests for AI Analyst service, authentication, grounding rules, and tenant isolation."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

os.environ.setdefault(
    "RAKSHAAI_DATABASE_URL",
    f"sqlite:///{Path(tempfile.NamedTemporaryFile(suffix='.db', delete=False).name).as_posix()}",
)

from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.ai_analyst import call_llm_provider  # noqa: E402
from app.services.rag import index_document, seed_knowledge_docs  # noqa: E402

init_db()
client = TestClient(app)


def _signup(org_name: str) -> dict:
    email = f"ai_user_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/signup", json={
        "email": email, "password": "supersecret123",
        "org_name": org_name, "name": "Owner",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    body["email"] = email
    return body


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class AIAnalystAuthTests(unittest.TestCase):
    def test_unauthenticated_query_rejected(self):
        res = client.post("/api/ai-analyst/query", json={"query": "What is card testing?"})
        self.assertEqual(res.status_code, 401)


class AIAnalystGroundingAndIsolationTests(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        seed_knowledge_docs(self.db)
        self.db.close()

    def test_authenticated_grounded_query(self):
        a = _signup("Analyst Org A")
        headers = _auth(a["access_token"])

        # Query seeded platform knowledge
        res = client.post("/api/ai-analyst/query", json={
            "query": "Card Testing Attack typology",
        }, headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("query", data)
        self.assertIn("answer", data)
        self.assertIn("sources", data)
        self.assertGreater(data["retrieved_chunks"], 0)
        self.assertTrue(len(data["sources"]) > 0)
        self.assertTrue("card" in data["answer"].lower() and "test" in data["answer"].lower())

    def test_ungrounded_query_returns_fallback_message(self):
        a = _signup("Analyst Org B")
        headers = _auth(a["access_token"])

        # Query completely outside system knowledge
        res = client.post("/api/ai-analyst/query", json={
            "query": "quantum orbit space shuttle mechanics",
        }, headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["answer"], "I don't have enough information in the system context to answer that.")

    def test_tenant_isolation_in_ai_analyst(self):
        a = _signup("Merchant Alpha AI")
        b = _signup("Merchant Beta AI")
        ha, hb = _auth(a["access_token"]), _auth(b["access_token"])

        # Merchant Alpha indexes private custom document
        db = SessionLocal()
        index_document(
            db=db,
            org_id=a["org"]["id"],
            doc_type="policy",
            title="Alpha Confidential Anti-Fraud Protocol",
            text="Alpha secret protocol 99: auto-block transactions with customer ID starting with ALPHA_BLK.",
        )
        db.close()

        # Merchant Alpha can retrieve its private protocol
        res_a = client.post("/api/ai-analyst/query", json={
            "query": "ALPHA_BLK auto-block protocol",
            "doc_type": "policy",
        }, headers=ha).json()
        self.assertTrue("ALPHA_BLK" in res_a["answer"] or "Alpha" in res_a["answer"] or len(res_a["sources"]) > 0)
        self.assertTrue(len(res_a["sources"]) > 0)

        # Merchant Beta MUST NOT retrieve Merchant Alpha's private protocol
        res_b = client.post("/api/ai-analyst/query", json={
            "query": "ALPHA_BLK auto-block protocol",
            "doc_type": "policy",
        }, headers=hb).json()
        self.assertEqual(res_b["answer"], "I don't have enough information in the system context to answer that.")
        self.assertEqual(res_b["sources"], [])


class GroqProviderTests(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        seed_knowledge_docs(self.db)
        self.db.close()

    @mock.patch("urllib.request.urlopen")
    def test_groq_provider_called_when_api_key_set(self, mock_urlopen):
        mock_response_body = json.dumps({
            "id": "chatcmpl-test-123",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Groq LLM response: Card testing attack detected with rapid low-value transactions.",
                    },
                    "finish_reason": "stop",
                }
            ],
        }).encode("utf-8")

        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = mock_response_body
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        a = _signup("Groq Org Test")
        headers = _auth(a["access_token"])

        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test_fake_key_123", "GROQ_MODEL": "llama-3.3-70b-versatile"}):
            res = client.post("/api/ai-analyst/query", json={
                "query": "What is card testing?",
            }, headers=headers)

            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["answer"], "Groq LLM response: Card testing attack detected with rapid low-value transactions.")
            self.assertTrue(mock_urlopen.called)

            # Inspect the outgoing Request object passed to urllib.request.urlopen
            req_arg = mock_urlopen.call_args[0][0]
            self.assertEqual(req_arg.get_header("Authorization"), "Bearer gsk_test_fake_key_123")
            self.assertEqual(req_arg.get_header("Content-type"), "application/json")
            req_payload = json.loads(req_arg.data.decode("utf-8"))
            self.assertEqual(req_payload["model"], "llama-3.3-70b-versatile")
            self.assertEqual(len(req_payload["messages"]), 2)
            self.assertEqual(req_payload["messages"][0]["role"], "system")
            self.assertEqual(req_payload["messages"][1]["role"], "user")
            self.assertEqual(req_payload["messages"][1]["content"], "What is card testing?")

    @mock.patch("urllib.request.urlopen")
    def test_groq_custom_model_from_env(self, mock_urlopen):
        mock_response_body = json.dumps({
            "choices": [
                {"message": {"role": "assistant", "content": "Analysis completed."}}
            ]
        }).encode("utf-8")
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = mock_response_body
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "gsk_custom_123", "GROQ_MODEL": "llama-3.1-8b-instant"}):
            ans = call_llm_provider("System prompt", "User query", [])
            self.assertEqual(ans, "Analysis completed.")
            req_arg = mock_urlopen.call_args[0][0]
            req_payload = json.loads(req_arg.data.decode("utf-8"))
            self.assertEqual(req_payload["model"], "llama-3.1-8b-instant")

    @mock.patch("urllib.request.urlopen")
    def test_groq_failure_falls_back_to_grounded_local_response(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Connection error to Groq API")

        context_chunks = [
            {
                "id": 1,
                "title": "Risk Policy",
                "content": "Threshold for manual review is 0.55.",
                "score": 0.85,
            }
        ]

        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "gsk_faulty_key_123"}):
            ans = call_llm_provider("System", "What is review threshold?", context_chunks)
            self.assertIn("Threshold for manual review is 0.55", ans)

    @mock.patch("urllib.request.urlopen")
    def test_groq_redacts_api_key_in_llm_response(self, mock_urlopen):
        mock_response_body = json.dumps({
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Here is the key: gsk_secret_123456789 and secret_hash: 9999abcdef",
                    }
                }
            ]
        }).encode("utf-8")
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = mock_response_body
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "gsk_secret_123456789"}):
            ans = call_llm_provider("System", "Show me keys", [])
            self.assertNotIn("gsk_secret_123456789", ans)
            self.assertIn("[REDACTED_API_KEY]", ans)


class AIConversationTests(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        seed_knowledge_docs(self.db)
        self.db.close()

    def test_conversation_crud_lifecycle(self):
        a = _signup("Conversation Org A")
        ha = _auth(a["access_token"])

        # 1. Create a new conversation
        res = client.post("/api/ai-analyst/conversations", json={"title": "Custom Investigation"}, headers=ha)
        self.assertEqual(res.status_code, 200)
        conv = res.json()
        conv_id = conv["id"]
        self.assertEqual(conv["title"], "Custom Investigation")
        self.assertEqual(len(conv["messages"]), 0)

        # 2. List conversations
        list_res = client.get("/api/ai-analyst/conversations", headers=ha)
        self.assertEqual(list_res.status_code, 200)
        items = list_res.json()
        self.assertTrue(any(c["id"] == conv_id for c in items))

        # 3. Query within conversation and verify message persistence
        q1 = client.post("/api/ai-analyst/query", json={
            "query": "What is card testing?",
            "conversation_id": conv_id,
        }, headers=ha)
        self.assertEqual(q1.status_code, 200)
        data1 = q1.json()
        self.assertEqual(data1["conversation_id"], conv_id)

        # 4. Fetch conversation details to verify persisted messages
        detail = client.get(f"/api/ai-analyst/conversations/{conv_id}", headers=ha).json()
        self.assertEqual(len(detail["messages"]), 2)  # 1 user + 1 assistant
        self.assertEqual(detail["messages"][0]["role"], "user")
        self.assertEqual(detail["messages"][0]["content"], "What is card testing?")
        self.assertEqual(detail["messages"][1]["role"], "assistant")

        # 5. Follow-up query in same conversation
        q2 = client.post("/api/ai-analyst/query", json={
            "query": "How is it mitigated?",
            "conversation_id": conv_id,
        }, headers=ha)
        self.assertEqual(q2.status_code, 200)

        detail2 = client.get(f"/api/ai-analyst/conversations/{conv_id}", headers=ha).json()
        self.assertEqual(len(detail2["messages"]), 4)  # 2 user + 2 assistant

        # 6. Rename conversation
        rename_res = client.patch(f"/api/ai-analyst/conversations/{conv_id}", json={"title": "Card Testing Deep Dive"}, headers=ha)
        self.assertEqual(rename_res.status_code, 200)
        self.assertEqual(rename_res.json()["title"], "Card Testing Deep Dive")

        # 7. Clear conversation
        clear_res = client.post(f"/api/ai-analyst/conversations/{conv_id}/clear", headers=ha)
        self.assertEqual(clear_res.status_code, 200)
        self.assertEqual(len(clear_res.json()["messages"]), 0)

        # 8. Delete conversation
        del_res = client.delete(f"/api/ai-analyst/conversations/{conv_id}", headers=ha)
        self.assertEqual(del_res.status_code, 200)

        get_deleted = client.get(f"/api/ai-analyst/conversations/{conv_id}", headers=ha)
        self.assertEqual(get_deleted.status_code, 404)

    def test_conversation_tenant_isolation(self):
        a = _signup("Tenant A")
        b = _signup("Tenant B")
        ha, hb = _auth(a["access_token"]), _auth(b["access_token"])

        # Org A creates conversation
        conv_a = client.post("/api/ai-analyst/conversations", json={"title": "Org A Secret Chat"}, headers=ha).json()
        conv_a_id = conv_a["id"]

        # Org B should NOT see Org A's conversation in list
        b_list = client.get("/api/ai-analyst/conversations", headers=hb).json()
        self.assertFalse(any(c["id"] == conv_a_id for c in b_list))

        # Org B cannot get Org A's conversation
        b_get = client.get(f"/api/ai-analyst/conversations/{conv_a_id}", headers=hb)
        self.assertEqual(b_get.status_code, 404)

        # Org B cannot rename Org A's conversation
        b_patch = client.patch(f"/api/ai-analyst/conversations/{conv_a_id}", json={"title": "Hacked"}, headers=hb)
        self.assertEqual(b_patch.status_code, 404)

        # Org B cannot delete Org A's conversation
        b_del = client.delete(f"/api/ai-analyst/conversations/{conv_a_id}", headers=hb)
        self.assertEqual(b_del.status_code, 404)

    def test_auto_create_and_title_generation(self):
        a = _signup("Auto Title Org")
        ha = _auth(a["access_token"])

        # Query without passing conversation_id creates a new conversation with auto-generated title
        res = client.post("/api/ai-analyst/query", json={
            "query": "Explain Account Takeover (ATO) patterns",
        }, headers=ha).json()

        self.assertIn("conversation_id", res)
        conv_id = res["conversation_id"]
        detail = client.get(f"/api/ai-analyst/conversations/{conv_id}", headers=ha).json()
        self.assertTrue("Account Takeover" in detail["title"] or "ATO" in detail["title"] or "Explain" in detail["title"])


class MoneySavedToolTests(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        seed_knowledge_docs(self.db)
        self.db.close()

    def test_get_money_saved_calculation_and_tenant_isolation(self):
        from datetime import datetime
        from app.models import Decision, Transaction
        from app.services.ai_analyst import get_money_saved
        from app.config import CHARGEBACK_FEE

        org_a = _signup("Merchant Money Alpha")
        org_b = _signup("Merchant Money Beta")
        ha, hb = _auth(org_a["access_token"]), _auth(org_b["access_token"])
        org_a_id = org_a["org"]["id"]
        org_b_id = org_b["org"]["id"]

        db = SessionLocal()
        now = datetime.utcnow()

        # Insert transactions for Org A:
        # Txn 1: ₹5,000 fraud, BLOCK action -> mitigated 100% = ₹5,000 + ₹1,500 = ₹6,500
        t1 = Transaction(
            org_id=org_a_id, txn_ref=f"TXN_A1_{uuid.uuid4().hex[:6]}", ts=now,
            customer_id="CUST1", card_hash="h1", card_bin="400000", card_type="credit",
            device_id="d1", ip="1.1.1.1", email="a1@test.com", email_domain="test.com",
            amount=5000.0, currency="INR", category="retail", channel="web",
            billing_country="IN", shipping_country="IN", is_fraud=1,
        )
        db.add(t1)
        db.flush()
        d1 = Decision(
            org_id=org_a_id, txn_id=t1.id, fraud_score=0.95, chargeback_score=0.8,
            risk_score=0.9, action="BLOCK", original_model_action="BLOCK", final_action="BLOCK",
            status="auto_blocked", threshold_block=0.82, threshold_review=0.55, threshold_challenge=0.35,
        )
        db.add(d1)

        # Txn 2: ₹2,000 fraud, STEP_UP action -> mitigated 70% = 0.7 * (₹2,000 + ₹1,500) = 0.7 * ₹3,500 = ₹2,450
        t2 = Transaction(
            org_id=org_a_id, txn_ref=f"TXN_A2_{uuid.uuid4().hex[:6]}", ts=now,
            customer_id="CUST2", card_hash="h2", card_bin="400000", card_type="credit",
            device_id="d2", ip="1.1.1.2", email="a2@test.com", email_domain="test.com",
            amount=2000.0, currency="INR", category="retail", channel="web",
            billing_country="IN", shipping_country="IN", is_fraud=1,
        )
        db.add(t2)
        db.flush()
        d2 = Decision(
            org_id=org_a_id, txn_id=t2.id, fraud_score=0.45, chargeback_score=0.4,
            risk_score=0.43, action="STEP_UP", original_model_action="STEP_UP", final_action="STEP_UP",
            status="stepped_up", threshold_block=0.82, threshold_review=0.55, threshold_challenge=0.35,
        )
        db.add(d2)

        # Txn 3: ₹10,000 legit, ALLOW action -> mitigated = 0
        t3 = Transaction(
            org_id=org_a_id, txn_ref=f"TXN_A3_{uuid.uuid4().hex[:6]}", ts=now,
            customer_id="CUST3", card_hash="h3", card_bin="400000", card_type="credit",
            device_id="d3", ip="1.1.1.3", email="a3@test.com", email_domain="test.com",
            amount=10000.0, currency="INR", category="retail", channel="web",
            billing_country="IN", shipping_country="IN", is_fraud=0,
        )
        db.add(t3)
        db.flush()
        d3 = Decision(
            org_id=org_a_id, txn_id=t3.id, fraud_score=0.05, chargeback_score=0.02,
            risk_score=0.04, action="ALLOW", original_model_action="ALLOW", final_action="ALLOW",
            status="auto_allowed", threshold_block=0.82, threshold_review=0.55, threshold_challenge=0.35,
        )
        db.add(d3)

        # Insert 1 transaction for Org B: ₹1,000 fraud, BLOCK action -> mitigated = ₹1,000 + ₹1,500 = ₹2,500
        t_b = Transaction(
            org_id=org_b_id, txn_ref=f"TXN_B1_{uuid.uuid4().hex[:6]}", ts=now,
            customer_id="CUST_B", card_hash="hb", card_bin="400000", card_type="credit",
            device_id="db", ip="2.2.2.2", email="b@test.com", email_domain="test.com",
            amount=1000.0, currency="INR", category="retail", channel="web",
            billing_country="IN", shipping_country="IN", is_fraud=1,
        )
        db.add(t_b)
        db.flush()
        d_b = Decision(
            org_id=org_b_id, txn_id=t_b.id, fraud_score=0.9, chargeback_score=0.9,
            risk_score=0.9, action="BLOCK", original_model_action="BLOCK", final_action="BLOCK",
            status="auto_blocked", threshold_block=0.82, threshold_review=0.55, threshold_challenge=0.35,
        )
        db.add(d_b)

        db.commit()
        db.close()

        # Expected for Org A: ₹6,500 + ₹2,450 = ₹8,950.00
        db = SessionLocal()
        saved_a = get_money_saved(db, org_a_id)
        self.assertEqual(saved_a["money_saved"], 8950.0)
        self.assertEqual(saved_a["total_transactions"], 3)
        self.assertEqual(saved_a["fraud_transactions_detected"], 2)
        self.assertEqual(saved_a["loss_mitigated_transactions"], 2)

        # Expected for Org B: ₹2,500.00
        saved_b = get_money_saved(db, org_b_id)
        self.assertEqual(saved_b["money_saved"], 2500.0)
        self.assertEqual(saved_b["total_transactions"], 1)
        self.assertEqual(saved_b["fraud_transactions_detected"], 1)
        self.assertEqual(saved_b["loss_mitigated_transactions"], 1)
        db.close()

        # Query AI Analyst endpoint for Org A
        res_a = client.post("/api/ai-analyst/query", json={
            "query": "How much money did we save today?",
        }, headers=ha).json()
        self.assertTrue("8,950" in res_a["answer"] or "8950" in res_a["answer"])
        self.assertTrue(any(s.get("title") == "Real-Time Risk Analytics" for s in res_a["sources"]))
        self.assertNotIn("get_money_saved", res_a["answer"])
        self.assertNotIn("student", res_a["answer"].lower())

        # Query AI Analyst endpoint for Org B
        res_b = client.post("/api/ai-analyst/query", json={
            "query": "How much money did we save today?",
        }, headers=hb).json()
        self.assertTrue("2,500" in res_b["answer"] or "2500" in res_b["answer"])
        self.assertFalse("8,950" in res_b["answer"] or "8950" in res_b["answer"])
        self.assertNotIn("get_money_saved", res_b["answer"])
        self.assertNotIn("student", res_b["answer"].lower())


class TransactionToolTests(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        seed_knowledge_docs(self.db)
        self.db.close()

    def test_get_transaction_successful_lookup(self):
        from datetime import datetime
        from app.models import Decision, Transaction
        from app.services.ai_analyst import get_transaction

        org_a = _signup("Merchant Txn Alpha")
        ha = _auth(org_a["access_token"])
        org_a_id = org_a["org"]["id"]

        db = SessionLocal()
        now = datetime.utcnow()
        t = Transaction(
            org_id=org_a_id, txn_ref="TXN_ALPHA_101", ts=now,
            customer_id="CUST_ALPHA_1", card_hash="card_hash_123", card_bin="512345", card_type="credit",
            device_id="DEV_ALPHA_1", ip="192.168.1.50", email="alpha.shopper@example.com", email_domain="example.com",
            amount=15499.50, currency="INR", category="electronics", channel="mobile_app",
            billing_country="IN", shipping_country="IN", is_fraud=1,
        )
        db.add(t)
        db.flush()
        d = Decision(
            org_id=org_a_id, txn_id=t.id, fraud_score=0.91, chargeback_score=0.85,
            risk_score=0.88, action="BLOCK", original_model_action="BLOCK", final_action="BLOCK",
            status="auto_blocked", threshold_block=0.82, threshold_review=0.55, threshold_challenge=0.35,
            reason_codes=["VELOCITY_SPIKE", "HIGH_AMOUNT_NEW_ACCOUNT"],
            ring_flag=True, ring_size=4,
        )
        db.add(d)
        db.commit()
        txn_id = t.id
        db.close()

        # 1. Test direct python function get_transaction
        db = SessionLocal()
        record_by_id = get_transaction(db, org_a_id, txn_id)
        self.assertIsNotNone(record_by_id)
        self.assertEqual(record_by_id["transaction_id"], txn_id)
        self.assertEqual(record_by_id["txn_ref"], "TXN_ALPHA_101")
        self.assertEqual(record_by_id["amount"], 15499.50)
        self.assertEqual(record_by_id["fraud_score"], 0.91)
        self.assertEqual(record_by_id["risk_score"], 0.88)
        self.assertEqual(record_by_id["final_action"], "BLOCK")
        self.assertIn("VELOCITY_SPIKE", record_by_id["reason_codes"])
        self.assertTrue(record_by_id["ring_signals"]["ring_flag"])
        self.assertEqual(record_by_id["ring_signals"]["ring_size"], 4)
        self.assertEqual(record_by_id["customer_details"]["customer_id"], "CUST_ALPHA_1")
        self.assertEqual(record_by_id["payment_details"]["card_bin"], "512345")

        record_by_ref = get_transaction(db, org_a_id, "TXN_ALPHA_101")
        self.assertIsNotNone(record_by_ref)
        self.assertEqual(record_by_ref["transaction_id"], txn_id)
        db.close()

        # 2. Test query via AI Analyst endpoint
        res = client.post("/api/ai-analyst/query", json={
            "query": f"Why was transaction {txn_id} blocked?",
        }, headers=ha).json()

        self.assertIn("answer", res)
        self.assertTrue(str(txn_id) in res["answer"] or "15,499" in res["answer"] or "BLOCK" in res["answer"])
        self.assertNotIn("get_transaction", res["answer"])
        self.assertNotIn("student", res["answer"].lower())
        self.assertTrue(any(s.get("id") == txn_id for s in res["sources"]))

    def test_get_transaction_missing_lookup(self):
        from app.services.ai_analyst import get_transaction

        org = _signup("Merchant Missing Txn")
        ha = _auth(org["access_token"])
        org_id = org["org"]["id"]

        db = SessionLocal()
        missing_record = get_transaction(db, org_id, 987654)
        self.assertIsNone(missing_record)
        db.close()

        res = client.post("/api/ai-analyst/query", json={
            "query": "What happened to transaction 987654?",
        }, headers=ha).json()

        self.assertIn("answer", res)
        self.assertTrue("not found" in res["answer"].lower() or "not exist" in res["answer"].lower() or "987654" in res["answer"])
        self.assertNotIn("get_transaction", res["answer"])

    def test_get_transaction_tenant_isolation(self):
        from datetime import datetime
        from app.models import Decision, Transaction
        from app.services.ai_analyst import get_transaction

        org_a = _signup("Tenant A Txn")
        org_b = _signup("Tenant B Txn")
        ha, hb = _auth(org_a["access_token"]), _auth(org_b["access_token"])
        org_a_id = org_a["org"]["id"]
        org_b_id = org_b["org"]["id"]

        db = SessionLocal()
        now = datetime.utcnow()
        t_a = Transaction(
            org_id=org_a_id, txn_ref="TXN_A_SECRET_999", ts=now,
            customer_id="CUST_SECRET_A", card_hash="hash_a", card_bin="411111", card_type="credit",
            device_id="DEV_A", ip="10.0.0.1", email="secret_a@tenant.com", email_domain="tenant.com",
            amount=42000.0, currency="INR", category="jewelry", channel="web",
            billing_country="IN", shipping_country="IN", is_fraud=1,
        )
        db.add(t_a)
        db.flush()
        d_a = Decision(
            org_id=org_a_id, txn_id=t_a.id, fraud_score=0.99, chargeback_score=0.95,
            risk_score=0.98, action="BLOCK", original_model_action="BLOCK", final_action="BLOCK",
            status="auto_blocked", threshold_block=0.82, threshold_review=0.55, threshold_challenge=0.35,
            reason_codes=["ATO_VELOCITY"], ring_flag=False, ring_size=0,
        )
        db.add(d_a)
        db.commit()
        t_a_id = t_a.id
        db.close()

        # Tenant A can access its transaction
        db = SessionLocal()
        self.assertIsNotNone(get_transaction(db, org_a_id, t_a_id))

        # Tenant B CANNOT access Tenant A's transaction
        self.assertIsNone(get_transaction(db, org_b_id, t_a_id))
        self.assertIsNone(get_transaction(db, org_b_id, "TXN_A_SECRET_999"))
        db.close()

        # Tenant B querying Tenant A's transaction via AI Analyst receives "not found"
        res_b = client.post("/api/ai-analyst/query", json={
            "query": f"Why was transaction {t_a_id} blocked?",
        }, headers=hb).json()

        self.assertTrue("not found" in res_b["answer"].lower() or "not exist" in res_b["answer"].lower() or "42000" not in res_b["answer"])
        self.assertNotIn("secret_a@tenant.com", res_b["answer"])
        self.assertNotIn("TXN_A_SECRET_999", res_b["answer"])


if __name__ == "__main__":
    unittest.main()



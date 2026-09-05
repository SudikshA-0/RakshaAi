"""Phase 1 guarantees: authentication and hard multi-tenant isolation.

These exercise the full HTTP stack (routing, auth dependency, tenant scoping)
against an isolated temporary database, so they prove that one merchant can
never read or mutate another merchant's data — the mandatory SaaS invariant.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# Bind the ORM engine to a throwaway database BEFORE importing the app. If the
# buildathon test module already bound one in this process, we share it — the
# isolation assertions below are all relative to orgs created inside each test,
# so a shared DB does not weaken them.
os.environ.setdefault(
    "RAKSHAAI_DATABASE_URL",
    f"sqlite:///{Path(tempfile.NamedTemporaryFile(suffix='.db', delete=False).name).as_posix()}",
)

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()  # create tables + demo tenant; does NOT seed (seeding lives in lifespan)
# Instantiated without the context manager so the seeding lifespan does not run.
client = TestClient(app)


def _signup(org_name: str) -> dict:
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
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


def _sample_txn(tag: str) -> dict:
    return {
        "amount": 1234.0,
        "customer_id": f"CUST_{tag}",
        "card_hash": f"tok_{tag}",
        "device_id": f"dev_{tag}",
        "ip": "49.10.20.30",
        "email": f"{tag}@gmail.com",
    }


class AuthTests(unittest.TestCase):
    def test_signup_returns_token_and_me_matches(self):
        a = _signup("Acme Payments")
        self.assertTrue(a["access_token"])
        self.assertEqual(a["token_type"], "bearer")
        self.assertEqual(a["org"]["name"], "Acme Payments")

        me = client.get("/api/auth/me", headers=_auth(a["access_token"]))
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["org"]["id"], a["org"]["id"])
        self.assertEqual(me.json()["user"]["email"], a["email"])

    def test_duplicate_email_conflicts(self):
        a = _signup("Dup Co")
        r = client.post("/api/auth/signup", json={
            "email": a["email"], "password": "supersecret123",
            "org_name": "Another", "name": "X",
        })
        self.assertEqual(r.status_code, 409)

    def test_login_wrong_password_rejected(self):
        a = _signup("Login Co")
        ok = client.post("/api/auth/login",
                         json={"email": a["email"], "password": "supersecret123"})
        self.assertEqual(ok.status_code, 200)
        bad = client.post("/api/auth/login",
                          json={"email": a["email"], "password": "wrong-password"})
        self.assertEqual(bad.status_code, 401)

    def test_unauthenticated_requests_rejected(self):
        for path in ("/api/transactions", "/api/analytics/overview",
                     "/api/cases", "/api/policy"):
            r = client.get(path)
            self.assertEqual(r.status_code, 401, f"{path} should require auth")


class TenantIsolationTests(unittest.TestCase):
    def test_merchant_cannot_read_or_mutate_another_tenant(self):
        a = _signup("Merchant A")
        b = _signup("Merchant B")
        ta, tb = _auth(a["access_token"]), _auth(b["access_token"])

        # Merchant A ingests a transaction of its own.
        created = client.post("/api/transactions", json=_sample_txn("A"), headers=ta)
        self.assertEqual(created.status_code, 200, created.text)
        a_txn = created.json()
        a_txn_id = a_txn["id"]
        a_decision_id = a_txn["decision_id"]
        a_ref = a_txn["txn_ref"]

        # A sees its own transaction in the list...
        a_list = client.get("/api/transactions", headers=ta).json()["transactions"]
        self.assertIn(a_ref, {t["txn_ref"] for t in a_list})

        # ...but B's list must never contain A's transaction.
        b_list = client.get("/api/transactions", headers=tb).json()["transactions"]
        self.assertNotIn(a_ref, {t["txn_ref"] for t in b_list})

        # B cannot fetch A's transaction by id (no IDOR).
        self.assertEqual(client.get(f"/api/transactions/{a_txn_id}", headers=tb).status_code, 404)
        # A still can.
        self.assertEqual(client.get(f"/api/transactions/{a_txn_id}", headers=ta).status_code, 200)

        # B cannot resolve A's case (no cross-tenant write).
        resolve = client.post(f"/api/cases/{a_decision_id}/resolve",
                              json={"analyst_label": 1, "note": "hijack"}, headers=tb)
        self.assertEqual(resolve.status_code, 404)

        # A's analytics count the transaction; B's do not.
        self.assertGreaterEqual(client.get("/api/analytics/overview", headers=ta).json()["total_transactions"], 1)
        self.assertEqual(client.get("/api/analytics/overview", headers=tb).json()["total_transactions"], 0)

    def test_api_keys_are_tenant_scoped_and_score_with_the_existing_pipeline(self):
        a = _signup("API Key A")
        b = _signup("API Key B")
        ta, tb = _auth(a["access_token"]), _auth(b["access_token"])

        created = client.post("/api/developer/keys", json={
            "name": "Sandbox integration", "environment": "sandbox",
        }, headers=ta)
        self.assertEqual(created.status_code, 201, created.text)
        key = created.json()
        self.assertTrue(key["api_key"].startswith("rsk_test_"))
        self.assertNotIn("secret_hash", key)

        listed = client.get("/api/developer/keys", headers=ta)
        self.assertEqual(listed.status_code, 200)
        self.assertNotIn("api_key", listed.json()["keys"][0])
        self.assertEqual(client.get("/api/developer/keys", headers=tb).json()["keys"], [])

        score = client.post("/api/v1/risk/score", json=_sample_txn("api"), headers={
            "X-API-Key": key["api_key"],
        })
        self.assertEqual(score.status_code, 200, score.text)
        body = score.json()
        self.assertIn("request_id", body)
        self.assertIn("model_version", body)
        self.assertIn("risk_signals", body)
        self.assertIn(body["decision"], {"ALLOW", "STEP_UP", "HOLD", "BLOCK"})

        # Dashboard authentication cannot reveal or revoke another tenant's key.
        self.assertEqual(client.post(f"/api/developer/keys/{key['id']}/revoke", headers=tb).status_code, 404)
        self.assertEqual(client.post(f"/api/developer/keys/{key['id']}/revoke", headers=ta).status_code, 200)
        self.assertEqual(client.post("/api/v1/risk/score", json=_sample_txn("revoked"), headers={
            "X-API-Key": key["api_key"],
        }).status_code, 401)

    def test_policy_is_per_tenant(self):
        a = _signup("Policy A")
        b = _signup("Policy B")
        ta, tb = _auth(a["access_token"]), _auth(b["access_token"])

        upd = client.put("/api/policy", json={"risk_appetite": 0.9}, headers=ta)
        self.assertEqual(upd.status_code, 200)
        self.assertAlmostEqual(upd.json()["risk_appetite"], 0.9)

        # B's policy is untouched by A's change.
        b_pol = client.get("/api/policy", headers=tb).json()
        self.assertNotAlmostEqual(b_pol["risk_appetite"], 0.9)
        # A's change persisted for A.
        a_pol = client.get("/api/policy", headers=ta).json()
        self.assertAlmostEqual(a_pol["risk_appetite"], 0.9)


if __name__ == "__main__":
    unittest.main()

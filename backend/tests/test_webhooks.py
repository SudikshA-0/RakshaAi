"""Tests for tenant-scoped, HMAC-signed webhooks and delivery execution."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
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
from app.models import Webhook, WebhookDelivery  # noqa: E402
from app.services.webhooks import decrypt_secret, sign_body, encode_payload  # noqa: E402

init_db()
client = TestClient(app)


def _signup(org_name: str) -> dict:
    email = f"wh_user_{uuid.uuid4().hex[:8]}@example.com"
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
        "amount": 1500.0,
        "customer_id": f"CUST_{tag}",
        "card_hash": f"tok_{tag}",
        "device_id": f"dev_{tag}",
        "ip": "49.10.20.30",
        "email": f"{tag}@gmail.com",
    }


class WebhookCRUDTests(unittest.TestCase):
    def test_create_list_update_disable_rotate(self):
        a = _signup("Webhook Org A")
        headers = _auth(a["access_token"])

        # 1. Create webhook
        res = client.post("/api/developer/webhooks", json={
            "name": "Primary Webhook",
            "url": "https://example.com/webhooks/rakshaai",
            "description": "Main notifications",
        }, headers=headers)
        self.assertEqual(res.status_code, 201, res.text)
        data = res.json()
        self.assertEqual(data["name"], "Primary Webhook")
        self.assertEqual(data["url"], "https://example.com/webhooks/rakshaai")
        self.assertTrue(data["enabled"])
        self.assertTrue(data["signing_secret"].startswith("whsec_"))
        hook_id = data["id"]
        secret1 = data["signing_secret"]

        # 2. List webhooks (must NOT contain signing_secret)
        listed = client.get("/api/developer/webhooks", headers=headers)
        self.assertEqual(listed.status_code, 200)
        hooks = listed.json()["webhooks"]
        self.assertEqual(len(hooks), 1)
        self.assertEqual(hooks[0]["id"], hook_id)
        self.assertNotIn("signing_secret", hooks[0])
        self.assertNotIn("secret_encrypted", hooks[0])

        # 3. Update webhook
        upd = client.patch(f"/api/developer/webhooks/{hook_id}", json={
            "name": "Updated Webhook Name",
        }, headers=headers)
        self.assertEqual(upd.status_code, 200)
        self.assertEqual(upd.json()["name"], "Updated Webhook Name")

        # 4. Disable webhook
        dis = client.post(f"/api/developer/webhooks/{hook_id}/disable", headers=headers)
        self.assertEqual(dis.status_code, 200)
        self.assertFalse(dis.json()["enabled"])

        # 5. Enable webhook
        ena = client.post(f"/api/developer/webhooks/{hook_id}/enable", headers=headers)
        self.assertEqual(ena.status_code, 200)
        self.assertTrue(ena.json()["enabled"])

        # 6. Rotate secret
        rot = client.post(f"/api/developer/webhooks/{hook_id}/rotate-secret", headers=headers)
        self.assertEqual(rot.status_code, 200)
        secret2 = rot.json()["signing_secret"]
        self.assertTrue(secret2.startswith("whsec_"))
        self.assertNotEqual(secret1, secret2)

        # 7. Delete (soft disable)
        dele = client.delete(f"/api/developer/webhooks/{hook_id}", headers=headers)
        self.assertEqual(dele.status_code, 200)
        self.assertFalse(dele.json()["enabled"])


class WebhookTenantIsolationTests(unittest.TestCase):
    def test_cross_tenant_access_prevented(self):
        a = _signup("Tenant Alpha")
        b = _signup("Tenant Beta")
        ha, hb = _auth(a["access_token"]), _auth(b["access_token"])

        # Alpha creates a webhook
        res = client.post("/api/developer/webhooks", json={
            "name": "Alpha Hook",
            "url": "https://alpha.example.com/events",
        }, headers=ha)
        hook_id = res.json()["id"]

        # Beta cannot see Alpha's webhook
        beta_list = client.get("/api/developer/webhooks", headers=hb).json()["webhooks"]
        self.assertNotIn(hook_id, [h["id"] for h in beta_list])

        # Beta cannot disable Alpha's webhook
        self.assertEqual(client.post(f"/api/developer/webhooks/{hook_id}/disable", headers=hb).status_code, 404)

        # Beta cannot rotate Alpha's secret
        self.assertEqual(client.post(f"/api/developer/webhooks/{hook_id}/rotate-secret", headers=hb).status_code, 404)

        # Beta cannot list Alpha's deliveries
        self.assertEqual(client.get(f"/api/developer/webhooks/{hook_id}/deliveries", headers=hb).status_code, 404)

        # Beta cannot trigger test event on Alpha's webhook
        self.assertEqual(client.post(f"/api/developer/webhooks/{hook_id}/test", headers=hb).status_code, 404)


class WebhookSSRFAndSignatureTests(unittest.TestCase):
    def test_ssrf_validation(self):
        a = _signup("SSRF Test Org")
        headers = _auth(a["access_token"])

        # Invalid scheme / localhost / private IP targeting
        bad_urls = [
            "ftp://example.com/webhook",
            "http://localhost:8000/webhook",
            "http://127.0.0.1/hook",
            "http://169.254.169.254/latest/meta-data/",
            "http://metadata.google.internal/computeMetadata",
        ]
        for url in bad_urls:
            res = client.post("/api/developer/webhooks", json={
                "name": "Bad URL",
                "url": url,
            }, headers=headers)
            self.assertIn(res.status_code, (400, 422), f"Expected 400 or 422 for {url}, got {res.status_code}")

    def test_signature_and_delivery_enqueuing(self):
        a = _signup("Delivery Test Org")
        headers = _auth(a["access_token"])

        # Create valid webhook
        created = client.post("/api/developer/webhooks", json={
            "name": "Valid Endpoint",
            "url": "https://webhook.site/test-endpoint",
        }, headers=headers).json()
        hook_id = created["id"]
        secret = created["signing_secret"]

        # Ingest a transaction which triggers risk scoring and webhook enqueuing
        txn_res = client.post("/api/transactions", json=_sample_txn("wh_sig"), headers=headers)
        self.assertEqual(txn_res.status_code, 200)

        # Check that delivery records were created
        deliv_res = client.get(f"/api/developer/webhooks/{hook_id}/deliveries", headers=headers)
        self.assertEqual(deliv_res.status_code, 200)
        deliveries = deliv_res.json()["deliveries"]
        self.assertGreaterEqual(len(deliveries), 1)

        # Test HMAC signature verification logic
        test_payload = {"event_id": "evt_test123", "event_type": "risk.decision.created"}
        body = encode_payload(test_payload)
        expected_sig = sign_body(secret, body)
        self.assertEqual(len(expected_sig), 64)  # SHA256 hex string length

        # Send test event
        test_res = client.post(f"/api/developer/webhooks/{hook_id}/test", headers=headers)
        self.assertEqual(test_res.status_code, 200)
        self.assertTrue(test_res.json()["test"])
        self.assertEqual(test_res.json()["delivery"]["event_type"], "webhook.test")


if __name__ == "__main__":
    unittest.main()

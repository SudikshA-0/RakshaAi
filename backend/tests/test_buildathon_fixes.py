"""Focused checks for the buildathon-critical integrity fixes."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["RAKSHAAI_DATABASE_URL"] = f"sqlite:///{Path(_tmp.name).as_posix()}"

from app.config import CHARGEBACK_FEE, LOSS_MITIGATION, potential_loss, prevented_loss  # noqa: E402
from app.database import SessionLocal, bootstrap_tenancy, init_db  # noqa: E402
from app.models import Decision, Organization, Transaction  # noqa: E402
from app.routers.analytics import overview, timeseries  # noqa: E402
from app.routers.cases import resolve_case  # noqa: E402
from app.schemas import FeedbackIn  # noqa: E402
from app.services.pipeline import get_policy_row, ingest_and_score, serialize  # noqa: E402
from app.services.simulator import attack_burst, demo_now  # noqa: E402


def _raw(**overrides):
    base = {
        "amount": 1000.0,
        "customer_id": "CUST00001",
        "card_hash": "tok_test_1",
        "card_bin": "402100",
        "card_type": "credit",
        "device_id": "dev_test_01",
        "ip": "49.1.2.3",
        "email": "user1@gmail.com",
        "category": "grocery",
        "channel": "mobile",
        "billing_country": "IN",
        "shipping_country": "IN",
        "account_age_days": 400,
        "ts": datetime(2026, 9, 4, 12, 0, 0),
        "is_fraud": 0,
        "is_chargeback": 0,
        "fraud_pattern": "legit",
    }
    base.update(overrides)
    return base


class MoneySavedTests(unittest.TestCase):
    def test_formula(self):
        self.assertEqual(potential_loss(1000), 1000 + CHARGEBACK_FEE)
        self.assertEqual(prevented_loss(1000, "BLOCK", 1), 1000 + CHARGEBACK_FEE)
        self.assertEqual(prevented_loss(1000, "HOLD", 1), 1000 + CHARGEBACK_FEE)
        self.assertAlmostEqual(prevented_loss(1000, "STEP_UP", 1), 0.7 * (1000 + CHARGEBACK_FEE))
        self.assertEqual(prevented_loss(1000, "ALLOW", 1), 0.0)
        self.assertEqual(prevented_loss(1000, "BLOCK", 0), 0.0)
        self.assertEqual(LOSS_MITIGATION["STEP_UP"], 0.7)


class AttackPatternTests(unittest.TestCase):
    def test_account_takeover_is_distinct(self):
        ato = attack_burst("account_takeover", count=8)
        ct = attack_burst("card_testing", count=8)
        hv = attack_burst("high_value", count=8)
        self.assertTrue(all(r["fraud_pattern"] == "account_takeover" for r in ato))
        self.assertTrue(all(r["fraud_pattern"] == "card_testing" for r in ct))
        self.assertTrue(all(r["fraud_pattern"] == "high_value" for r in hv))
        self.assertEqual(len({r["customer_id"] for r in ato}), 1)
        self.assertEqual(len({r["card_hash"] for r in ato}), 1)
        self.assertEqual(len({r["device_id"] for r in ato}), 1)
        self.assertGreater(len({r["card_hash"] for r in ct}), 1)
        self.assertTrue(all(r["billing_country"] == "IN" for r in ato))
        self.assertTrue(all(r["shipping_country"] != "IN" for r in ato))
        self.assertTrue(all(r["amount"] > 1000 for r in ato))
        self.assertTrue(all(r["amount"] < 1000 for r in ct))


class PipelineIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.db = SessionLocal()
        cls.org_id = bootstrap_tenancy().id
        cls.org = cls.db.get(Organization, cls.org_id)   # bound to this session
        get_policy_row(cls.db, cls.org_id)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_models_load_and_score(self):
        txn, decision = ingest_and_score(self.db, _raw(amount=250.0), self.org_id, source="live")
        self.assertIsNotNone(decision.fraud_score)
        self.assertIsNotNone(decision.chargeback_score)
        self.assertEqual(decision.original_model_action, decision.action)
        self.assertEqual(decision.final_action, decision.action)
        self.assertFalse(decision.analyst_override)
        self.assertIn(decision.action, ("ALLOW", "STEP_UP", "HOLD", "BLOCK"))
        self.assertTrue(txn.txn_ref.startswith("TXN"))

    def test_analyst_resolution_preserves_original_model_action(self):
        txn, decision = ingest_and_score(
            self.db,
            _raw(
                amount=1800.0,
                customer_id="CUST_HOLD",
                card_hash="tok_hold",
                device_id="dev_hold",
                is_fraud=0,
            ),
            self.org_id,
            source="live",
        )
        original = decision.original_model_action
        payload = FeedbackIn(analyst_label=0, note="false positive")
        out = resolve_case(decision.id, payload, self.db, self.org)
        self.assertEqual(out["original_model_action"], original)
        self.assertEqual(out["final_action"], "ALLOW")
        self.assertEqual(out["action"], "ALLOW")
        self.assertEqual(out["analyst_label"], 0)
        refreshed = self.db.get(Decision, decision.id)
        self.assertEqual(refreshed.original_model_action, original)
        self.assertEqual(refreshed.final_action, "ALLOW")
        self.assertEqual(refreshed.analyst_override, original != "ALLOW")

    def test_metrics_use_original_not_final_action(self):
        # Isolated fraud txn we force-label; then analyst releases it.
        txn, decision = ingest_and_score(
            self.db,
            _raw(
                amount=5000.0,
                customer_id="CUST_FRAUD_M",
                card_hash="tok_fraud_m",
                device_id="dev_fraud_m",
                category="gift_cards",
                channel="api",
                card_bin="411111",
                card_type="prepaid",
                billing_country="US",
                shipping_country="IN",
                account_age_days=2,
                email="buyer@mailinator.com",
                is_fraud=1,
                is_chargeback=1,
                fraud_pattern="stolen_card",
            ),
            self.org_id,
            source="live",
        )
        original = decision.original_model_action
        resolve_case(decision.id, FeedbackIn(analyst_label=0, note="released"), self.db, self.org)
        ov = overview(self.db, self.org)
        # precision/recall must still see the original model action for this row
        self.assertIn("precision", ov)
        self.assertIn("analyst_overrides", ov)
        rows = self.db.query(Decision).filter(Decision.txn_id == txn.id).one()
        self.assertEqual(rows.original_model_action, original)
        self.assertEqual(rows.final_action, "ALLOW")

    def test_money_saved_matches_timeseries_formula(self):
        db = self.db
        rows = (db.query(Transaction, Decision).join(Decision)
                .filter(Transaction.org_id == self.org_id).all())
        expected = sum(
            prevented_loss(t.amount, d.original_model_action or d.action, t.is_fraud)
            for t, d in rows
        )
        ov = overview(db, self.org)
        self.assertAlmostEqual(ov["money_saved"], round(expected, 2), places=2)
        ts = timeseries(db, self.org, days=60)
        series_saved = sum(p["saved"] for p in ts["series"])
        self.assertAlmostEqual(series_saved, ov["money_saved"], places=2)

    def test_card_testing_and_ato_through_pipeline(self):
        ct = attack_burst("card_testing", count=6, db=self.db, org_id=self.org_id)
        self.assertEqual(ct[0]["fraud_pattern"], "card_testing")
        t, d = ingest_and_score(self.db, ct[0], self.org_id, source="attack")
        self.assertEqual(t.fraud_pattern, "card_testing")
        self.assertEqual(d.original_model_action, d.action)

        ato = attack_burst("account_takeover", count=6, db=self.db, org_id=self.org_id)
        self.assertEqual(ato[0]["fraud_pattern"], "account_takeover")
        devices = {r["device_id"] for r in ato}
        cards = {r["card_hash"] for r in ato}
        self.assertEqual(len(devices), 1)
        self.assertEqual(len(cards), 1)
        scored = []
        for raw in ato:
            scored.append(ingest_and_score(self.db, raw, self.org_id, source="attack", commit=False))
        self.db.commit()
        self.assertTrue(any(d.ring_flag or d.original_model_action != "ALLOW" for _, d in scored))

    def test_demo_now_tracks_latest_when_stale(self):
        from sqlalchemy import func
        newest = self.db.execute(
            select(func.max(Transaction.ts)).where(Transaction.org_id == self.org_id)
        ).scalar()
        clock = demo_now(self.db, self.org_id)
        gap = datetime.utcnow() - newest
        if gap > timedelta(hours=24):
            self.assertLess((clock - newest).total_seconds(), 60)
        else:
            self.assertGreaterEqual(clock, newest)

    def test_serialize_exposes_integrity_fields(self):
        txn, decision = ingest_and_score(self.db, _raw(customer_id="CUST_SER", card_hash="tok_ser", device_id="dev_ser"), self.org_id)
        data = serialize(txn, decision)
        self.assertIn("original_model_action", data)
        self.assertIn("final_action", data)
        self.assertIn("analyst_override", data)
        self.assertIn("analyst_label", data)


if __name__ == "__main__":
    unittest.main()

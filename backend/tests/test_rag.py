"""Tests for RAG foundation: chunking, embedding generation, vector storage, cosine retrieval, and tenant isolation."""
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

from app.database import SessionLocal, bootstrap_tenancy, init_db  # noqa: E402
from app.models import AIEmbedding, Organization  # noqa: E402
from app.services.rag import (  # noqa: E402
    chunk_text,
    cosine_similarity,
    get_embedding,
    index_document,
    retrieve_context,
    seed_knowledge_docs,
)

init_db()


class RAGChunkingTests(unittest.TestCase):
    def test_empty_and_short_text(self):
        self.assertEqual(chunk_text(""), [])
        self.assertEqual(chunk_text("  "), [])
        short = "Short document content."
        chunks = chunk_text(short, chunk_size=100)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], short)

    def test_paragraph_chunking(self):
        text = "Paragraph 1 is about risk scoring.\n\nParagraph 2 is about fraud models.\n\nParagraph 3 is about chargeback rates."
        chunks = chunk_text(text, chunk_size=45, overlap=10)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(any("Paragraph 1" in c for c in chunks))
        self.assertTrue(any("Paragraph 3" in c for c in chunks))


class EmbeddingAndStorageTests(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def test_vector_generation(self):
        vec1 = get_embedding("fraud detection engine", dim=32)
        self.assertEqual(len(vec1), 32)
        self.assertTrue(all(isinstance(v, float) for v in vec1))

        # Vector should be normalized
        norm = sum(v * v for v in vec1) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=3)

    def test_index_and_persist_in_sqlite(self):
        title = "Merchant Risk Guide"
        text = "Detailed policy guidelines for high-value transactions and automated risk actions."
        records = index_document(
            db=self.db,
            org_id=1,
            doc_type="policy_doc",
            title=title,
            text=text,
            meta_data={"author": "risk_team"},
        )
        self.assertGreaterEqual(len(records), 1)

        # Retrieve raw ORM record from SQLite
        db_rec = self.db.get(AIEmbedding, records[0].id)
        self.assertIsNotNone(db_rec)
        self.assertEqual(db_rec.title, title)
        self.assertEqual(db_rec.org_id, 1)
        self.assertEqual(db_rec.doc_type, "policy_doc")
        self.assertIsInstance(db_rec.vector, list)
        self.assertEqual(len(db_rec.vector), 64)


class CosineRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.org_id = 999

    def tearDown(self):
        self.db.close()

    def test_cosine_similarity_math(self):
        v1 = [1.0, 0.0, 0.0]
        v2 = [1.0, 0.0, 0.0]
        v3 = [0.0, 1.0, 0.0]
        self.assertAlmostEqual(cosine_similarity(v1, v2), 1.0)
        self.assertAlmostEqual(cosine_similarity(v1, v3), 0.0)

    def test_relevant_chunk_ranking(self):
        index_document(
            db=self.db,
            org_id=self.org_id,
            doc_type="guide",
            title="Card Testing",
            text="Card testing attacks involve rapid low value velocity transactions across multiple BIN numbers.",
        )
        index_document(
            db=self.db,
            org_id=self.org_id,
            doc_type="guide",
            title="Refund Policy",
            text="Standard customer refund and dispute resolution policy guidelines.",
        )

        results = retrieve_context(self.db, query="velocity card testing BIN", org_id=self.org_id, top_k=2)
        self.assertGreaterEqual(len(results), 1)
        # The Card Testing doc should be ranked first with higher score
        self.assertEqual(results[0]["title"], "Card Testing")
        self.assertGreater(results[0]["score"], 0.0)


class RAGTenantIsolationTests(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.org_a = Organization(name="Tenant Alpha RAG")
        self.org_b = Organization(name="Tenant Beta RAG")
        self.db.add_all([self.org_a, self.org_b])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_tenant_data_isolation(self):
        # Index document for Tenant A
        index_document(
            db=self.db,
            org_id=self.org_a.id,
            doc_type="confidential",
            title="Alpha Strategy",
            text="Alpha secret merchant fraud rules and high-risk customer blacklist.",
        )

        # Index document for Tenant B
        index_document(
            db=self.db,
            org_id=self.org_b.id,
            doc_type="confidential",
            title="Beta Strategy",
            text="Beta secret merchant risk thresholds and operational procedures.",
        )

        # Seed global platform docs (org_id = None)
        seed_knowledge_docs(self.db)

        # Query as Tenant A
        res_a = retrieve_context(self.db, query="secret merchant rules", org_id=self.org_a.id, top_k=10)
        titles_a = {r["title"] for r in res_a}
        self.assertIn("Alpha Strategy", titles_a)
        self.assertNotIn("Beta Strategy", titles_a)  # Must NOT leak Tenant B's doc

        # Query as Tenant B
        res_b = retrieve_context(self.db, query="secret merchant rules", org_id=self.org_b.id, top_k=10)
        titles_b = {r["title"] for r in res_b}
        self.assertIn("Beta Strategy", titles_b)
        self.assertNotIn("Alpha Strategy", titles_b)  # Must NOT leak Tenant A's doc

        # Both tenants should see global knowledge docs (org_id = None)
        self.assertTrue(any(r["org_id"] is None for r in res_a))
        self.assertTrue(any(r["org_id"] is None for r in res_b))


if __name__ == "__main__":
    unittest.main()

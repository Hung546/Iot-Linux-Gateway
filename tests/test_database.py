"""
Unit tests for SQLite Storage Engine.
"""

import sys
import os
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gateway.database import DatabaseManager


class TestDatabaseManager(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_gateway.db")
        self.db = DatabaseManager(self.db_path, max_records=5)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_insert_and_idempotency(self):
        norm_data = {
            "schema_version": 1,
            "node_id": "esp32_01",
            "message_id": "msg_001",
            "timestamp": "2026-10-16T08:00:00Z",
            "sensors": {"temperature_c": 25.5, "humidity_pct": 60.0}
        }
        # First insert
        is_new, rec_id, status = self.db.insert_telemetry(norm_data, "{}", "127.0.0.1")
        self.assertTrue(is_new)
        self.assertEqual(rec_id, 1)

        # Duplicate insert with identical message_id
        is_new_dup, rec_id_dup, status_dup = self.db.insert_telemetry(norm_data, "{}", "127.0.0.1")
        self.assertFalse(is_new_dup)
        self.assertEqual(rec_id_dup, 1)
        self.assertIn("duplicate", status_dup)

        # Database should still contain only 1 record
        stats = self.db.get_stats()
        self.assertEqual(stats["total_records"], 1)

    def test_pending_queue_and_mark_sent(self):
        # Insert 3 records
        for i in range(1, 4):
            norm = {
                "schema_version": 1,
                "node_id": f"esp32_{i}",
                "message_id": f"msg_{i:03d}",
                "timestamp": f"2026-10-16T08:0{i}:00Z",
                "sensors": {"temperature_c": 20.0 + i}
            }
            self.db.insert_telemetry(norm, "{}", "127.0.0.1")

        pending = self.db.get_pending_records(limit=2)
        self.assertEqual(len(pending), 2)
        self.assertEqual(pending[0]["message_id"], "msg_001")
        self.assertEqual(pending[1]["message_id"], "msg_002")

        # Mark first record as SENT
        marked = self.db.mark_records_as_sent([pending[0]["id"]])
        self.assertEqual(marked, 1)

        # Remaining pending should be 2 records
        stats = self.db.get_stats()
        self.assertEqual(stats["pending_records"], 2)
        self.assertEqual(stats["sent_records"], 1)

    def test_retention_policy_purge_oldest_sent(self):
        # max_records is 5
        # Insert 4 records, mark them SENT
        for i in range(1, 5):
            norm = {
                "schema_version": 1,
                "node_id": "esp32_01",
                "message_id": f"sent_msg_{i}",
                "timestamp": "2026-10-16T08:00:00Z",
                "sensors": {"temperature_c": 25.0}
            }
            is_new, r_id, _ = self.db.insert_telemetry(norm, "{}", "127.0.0.1")
            self.db.mark_records_as_sent([r_id])

        # Insert 3 more records (pending)
        for i in range(5, 8):
            norm = {
                "schema_version": 1,
                "node_id": "esp32_01",
                "message_id": f"pending_msg_{i}",
                "timestamp": "2026-10-16T08:00:00Z",
                "sensors": {"temperature_c": 25.0}
            }
            self.db.insert_telemetry(norm, "{}", "127.0.0.1")

        stats = self.db.get_stats()
        # Total records should be kept under or around max_records (5)
        self.assertLessEqual(stats["total_records"], 5)
        # Pending records should be preserved
        self.assertEqual(stats["pending_records"], 3)


if __name__ == "__main__":
    unittest.main()

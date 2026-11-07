"""
Integration tests for Store-and-Forward Engine.
Simulates network outage, local buffering in SQLite, and reconnection drain.
"""

import sys
import os
import time
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gateway.database import DatabaseManager
from gateway.forwarder import CloudForwarder


class TestStoreAndForwardIntegration(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_snf.db")
        self.db = DatabaseManager(self.db_path)
        self.config = {
            "cloud_forwarder": {
                "enabled": True,
                "mock_mode": True,
                "batch_size": 10,
                "poll_interval_sec": 0.5
            }
        }
        self.forwarder = CloudForwarder(self.db, self.config)

    def tearDown(self):
        self.forwarder.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_store_and_forward_flow(self):
        # 1. Start forwarder in OFFLINE state
        self.forwarder.set_online_state(False)
        self.forwarder.start()

        # 2. Simulate ESP32 nodes sending data while network is down
        for i in range(1, 6):
            norm = {
                "schema_version": 1,
                "node_id": "esp32_01" if i % 2 == 1 else "esp32_02",
                "message_id": f"msg_offline_{i:03d}",
                "timestamp": f"2026-10-16T08:0{i}:00Z",
                "sensors": {"temperature_c": 28.0 + i, "humidity_pct": 65.0}
            }
            self.db.insert_telemetry(norm, "{}", "192.168.1.100")

        # Give forwarder thread time to cycle
        time.sleep(1.0)

        # 3. Verify all records are buffered as PENDING in SQLite (0 sent)
        stats = self.db.get_stats()
        self.assertEqual(stats["total_records"], 5)
        self.assertEqual(stats["pending_records"], 5)
        self.assertEqual(stats["sent_records"], 0)

        # 4. Now restore network connection (ONLINE)
        self.forwarder.set_online_state(True)

        # Give forwarder time to drain queue
        time.sleep(1.5)

        # 5. Verify all records have transitioned to SENT (0 lost)
        stats_after = self.db.get_stats()
        self.assertEqual(stats_after["pending_records"], 0)
        self.assertEqual(stats_after["sent_records"], 5)
        self.assertEqual(self.forwarder._forwarded_total, 5)


if __name__ == "__main__":
    unittest.main()

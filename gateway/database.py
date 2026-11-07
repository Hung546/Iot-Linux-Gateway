"""
SQLite Storage Engine for MYIR MYS-6ULX Gateway Daemon.
Implements ACID buffering, message deduplication (idempotency), WAL mode for flash protection,
and FIFO store-and-forward queue queries.
"""

import os
import json
import sqlite3
import logging
import threading
from datetime import datetime, timezone

logger = logging.getLogger("gateway.database")


class DatabaseManager:
    """Manages SQLite database operations with thread safety and WAL mode."""

    def __init__(self, db_path, max_records=50000):
        self.db_path = db_path
        self.max_records = max_records
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self):
        """Creates a connection with optimized pragmas for embedded Linux flash memory."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        # Write-Ahead Logging for concurrency and less flash memory wear on i.MX6
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA temp_store = MEMORY;")
        return conn

    def _init_db(self):
        """Initializes tables and indexes."""
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Table 1: Main Telemetry Buffer
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS telemetry (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_id TEXT UNIQUE NOT NULL,
                        node_id TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        schema_version INTEGER NOT NULL,
                        temperature_c REAL,
                        humidity_pct REAL,
                        pm25_ug_m3 REAL,
                        co2_ppm REAL,
                        raw_payload TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'PENDING',  -- 'PENDING', 'SENT', 'FAILED'
                        retry_count INTEGER DEFAULT 0,
                        last_error TEXT,
                        created_at TEXT NOT NULL,
                        sent_at TEXT
                    );
                """)

                # Indexes for fast FIFO polling and filtering
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_status_id ON telemetry (status, id);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_node_id ON telemetry (node_id);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_msg_id ON telemetry (message_id);")

                # Table 2: Node Registry (tracks active ESP32 nodes)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS node_registry (
                        node_id TEXT PRIMARY KEY,
                        first_seen TEXT NOT NULL,
                        last_seen TEXT NOT NULL,
                        total_messages INTEGER DEFAULT 0,
                        last_ip TEXT
                    );
                """)

                conn.commit()
                logger.info("SQLite database initialized at: %s", self.db_path)

    def insert_telemetry(self, norm_data, raw_payload_str, client_ip=""):
        """
        Inserts new telemetry record.
        Handles idempotency: if message_id exists, ignores duplicate and returns (is_new=False).
        Returns:
            tuple (is_new: bool, record_id: int, status_str: str)
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        node_id = norm_data["node_id"]
        message_id = norm_data["message_id"]
        sensors = norm_data.get("sensors", {})

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Check for existing message_id (Idempotency check)
                cursor.execute("SELECT id, status FROM telemetry WHERE message_id = ?", (message_id,))
                existing = cursor.fetchone()
                if existing:
                    logger.warning("Duplicate message detected: '%s' from node '%s' (status=%s). Skipping duplicate insert.",
                                   message_id, node_id, existing["status"])
                    # Update node last seen even on duplicate
                    self._update_node_registry(cursor, node_id, now_str, client_ip, increment=False)
                    conn.commit()
                    return False, existing["id"], f"duplicate (already {existing['status']})"

                # Insert new record
                cursor.execute("""
                    INSERT INTO telemetry (
                        message_id, node_id, timestamp, schema_version,
                        temperature_c, humidity_pct, pm25_ug_m3, co2_ppm,
                        raw_payload, status, retry_count, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', 0, ?)
                """, (
                    message_id,
                    node_id,
                    norm_data["timestamp"],
                    norm_data.get("schema_version", 1),
                    sensors.get("temperature_c"),
                    sensors.get("humidity_pct"),
                    sensors.get("pm25_ug_m3"),
                    sensors.get("co2_ppm"),
                    raw_payload_str,
                    now_str
                ))
                new_id = cursor.lastrowid

                # Update registry
                self._update_node_registry(cursor, node_id, now_str, client_ip, increment=True)

                # Check storage limit
                self._check_and_enforce_retention(cursor)

                conn.commit()
                logger.debug("Stored record #%d (message_id='%s', node='%s')", new_id, message_id, node_id)
                return True, new_id, "stored"

    def _update_node_registry(self, cursor, node_id, now_str, client_ip, increment=True):
        """Maintains tracking of active ESP32 nodes."""
        cursor.execute("SELECT node_id, total_messages FROM node_registry WHERE node_id = ?", (node_id,))
        row = cursor.fetchone()
        if row:
            inc_val = 1 if increment else 0
            cursor.execute("""
                UPDATE node_registry
                SET last_seen = ?, total_messages = total_messages + ?, last_ip = COALESCE(NULLIF(?, ''), last_ip)
                WHERE node_id = ?
            """, (now_str, inc_val, client_ip, node_id))
        else:
            cursor.execute("""
                INSERT INTO node_registry (node_id, first_seen, last_seen, total_messages, last_ip)
                VALUES (?, ?, ?, 1, ?)
            """, (node_id, now_str, now_str, client_ip))

    def _check_and_enforce_retention(self, cursor):
        """Enforces max_records policy: purge oldest SENT records first."""
        cursor.execute("SELECT COUNT(*) AS total FROM telemetry")
        total = cursor.fetchone()["total"]
        if total > self.max_records:
            excess = total - self.max_records
            cursor.execute("""
                DELETE FROM telemetry
                WHERE id IN (
                    SELECT id FROM telemetry
                    WHERE status = 'SENT'
                    ORDER BY id ASC
                    LIMIT ?
                )
            """, (excess,))
            purged = cursor.rowcount
            if purged > 0:
                logger.info("Storage policy: Purged %d oldest SENT records to maintain max limit %d", purged, self.max_records)
            else:
                logger.warning("Storage warning: Database has %d records, but none are marked 'SENT' to purge! Pending records are preserved.", total)

    def get_pending_records(self, limit=20):
        """Fetches batch of pending records in FIFO order for cloud forwarding."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, message_id, node_id, timestamp, schema_version,
                           temperature_c, humidity_pct, pm25_ug_m3, co2_ppm,
                           raw_payload, retry_count
                    FROM telemetry
                    WHERE status = 'PENDING'
                    ORDER BY id ASC
                    LIMIT ?
                """, (limit,))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]

    def mark_records_as_sent(self, record_ids):
        """Marks list of record IDs as successfully delivered to Cloud (SENT)."""
        if not record_ids:
            return 0
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ",".join(["?"] * len(record_ids))
                cursor.execute(f"""
                    UPDATE telemetry
                    SET status = 'SENT', sent_at = ?, last_error = NULL
                    WHERE id IN ({placeholders})
                """, [now_str] + record_ids)
                conn.commit()
                return cursor.rowcount

    def mark_records_failed(self, record_ids, error_msg):
        """Increments retry_count and logs error message."""
        if not record_ids:
            return 0
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ",".join(["?"] * len(record_ids))
                cursor.execute(f"""
                    UPDATE telemetry
                    SET retry_count = retry_count + 1, last_error = ?
                    WHERE id IN ({placeholders})
                """, [error_msg] + record_ids)
                conn.commit()
                return cursor.rowcount

    def get_stats(self):
        """Returns health and queue metrics."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) AS count FROM telemetry")
                total = cursor.fetchone()["count"]

                cursor.execute("SELECT COUNT(*) AS count FROM telemetry WHERE status = 'PENDING'")
                pending = cursor.fetchone()["count"]

                cursor.execute("SELECT COUNT(*) AS count FROM telemetry WHERE status = 'SENT'")
                sent = cursor.fetchone()["count"]

                cursor.execute("SELECT COUNT(*) AS count FROM node_registry")
                nodes_count = cursor.fetchone()["count"]

                db_size_bytes = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0

                return {
                    "total_records": total,
                    "pending_records": pending,
                    "sent_records": sent,
                    "active_nodes_count": nodes_count,
                    "db_size_bytes": db_size_bytes,
                    "db_size_kb": round(db_size_bytes / 1024.0, 2),
                    "db_path": self.db_path
                }

    def get_nodes(self):
        """Returns all registered nodes with their last telemetry info."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM node_registry ORDER BY last_seen DESC")
                return [dict(row) for row in cursor.fetchall()]

    def get_recent_telemetry(self, limit=10):
        """Returns recent telemetry entries for debugging and CLI display."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, message_id, node_id, timestamp, temperature_c,
                           humidity_pct, pm25_ug_m3, co2_ppm, status, retry_count, created_at, sent_at
                    FROM telemetry
                    ORDER BY id DESC
                    LIMIT ?
                """, (limit,))
                return [dict(row) for row in cursor.fetchall()]

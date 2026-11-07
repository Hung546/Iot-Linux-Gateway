"""
HTTP REST Ingestion Server for MYIR MYS-6ULX Gateway Daemon.
Runs multi-threaded on standard library (zero external dependencies).
Receives JSON telemetry from ESP32 nodes over local Wi-Fi / Ethernet.
"""

import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from datetime import datetime, timezone

from .validator import validate_telemetry_payload

logger = logging.getLogger("gateway.http")


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP server so concurrent node requests don't block each other."""
    daemon_threads = True
    allow_reuse_address = True


def make_request_handler(db_manager, forwarder_ref=None, start_time=None):
    """Factory to inject dependencies into BaseHTTPRequestHandler."""

    class TelemetryHTTPHandler(BaseHTTPRequestHandler):

        def log_message(self, format, *args):
            """Redirect default HTTP logging to python logging."""
            logger.debug("%s - - [%s] %s", self.address_string(), self.log_date_time_string(), format % args)

        def _send_json_response(self, status_code, data):
            """Helper to send standardized JSON response."""
            response_bytes = json.dumps(data, indent=2).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_bytes)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response_bytes)

        def do_OPTIONS(self):
            """Handle CORS pre-flight."""
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self):
            """Handles status and inspection requests."""
            path = self.path.split("?")[0].rstrip("/")

            if path in ("", "/api/v1/health"):
                uptime_sec = (datetime.now(timezone.utc) - start_time).total_seconds() if start_time else 0
                stats = db_manager.get_stats()
                cloud_status = forwarder_ref.get_status() if forwarder_ref else {"enabled": False}

                payload = {
                    "gateway": "MYIR MYS-6ULX-IND Environmental Gateway",
                    "status": "HEALTHY",
                    "uptime_seconds": round(uptime_sec, 1),
                    "database": stats,
                    "cloud_uplink": cloud_status,
                    "server_time_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                }
                self._send_json_response(200, payload)

            elif path == "/api/v1/nodes":
                nodes = db_manager.get_nodes()
                self._send_json_response(200, {"nodes": nodes, "count": len(nodes)})

            elif path == "/api/v1/telemetry/recent":
                recent = db_manager.get_recent_telemetry(limit=15)
                self._send_json_response(200, {"recent_telemetry": recent, "count": len(recent)})

            else:
                self._send_json_response(404, {"error": "Not Found", "valid_endpoints": [
                    "POST /api/v1/telemetry",
                    "GET /api/v1/health",
                    "GET /api/v1/nodes",
                    "GET /api/v1/telemetry/recent"
                ]})

        def do_POST(self):
            """Handles telemetry ingestion and simulator controls."""
            path = self.path.split("?")[0].rstrip("/")

            content_len = int(self.headers.get("Content-Length", 0))
            if content_len == 0:
                self._send_json_response(400, {"status": "error", "message": "Empty request body"})
                return

            try:
                body_bytes = self.rfile.read(content_len)
                body_str = body_bytes.decode("utf-8")
                payload = json.loads(body_str)
            except Exception as e:
                logger.warning("Failed to decode JSON from %s: %s", self.client_address[0], e)
                self._send_json_response(400, {"status": "error", "message": f"Malformed JSON: {str(e)}"})
                return

            if path == "/api/v1/telemetry":
                # Validate according to M0/M1 schema specification
                is_valid, err_msg, norm_data = validate_telemetry_payload(payload)
                if not is_valid:
                    logger.warning("Rejected telemetry from %s: %s", self.client_address[0], err_msg)
                    self._send_json_response(400, {
                        "status": "error",
                        "error_type": "ValidationError",
                        "message": err_msg
                    })
                    return

                # Insert into SQLite
                client_ip = self.client_address[0]
                is_new, record_id, action = db_manager.insert_telemetry(norm_data, body_str, client_ip)

                if is_new:
                    logger.info("Accepted telemetry from Node '%s' (msg_id: %s) -> DB record #%d",
                                norm_data['node_id'], norm_data['message_id'], record_id)
                    self._send_json_response(201, {
                        "status": "success",
                        "action": "stored",
                        "record_id": record_id,
                        "message_id": norm_data["message_id"],
                        "warnings": norm_data.get("warnings", [])
                    })
                else:
                    # Idempotent response for duplicate
                    logger.info("Idempotent duplicate acknowledged for Node '%s' (msg_id: %s)",
                                norm_data['node_id'], norm_data['message_id'])
                    self._send_json_response(200, {
                        "status": "success",
                        "action": "duplicate_ignored",
                        "record_id": record_id,
                        "message_id": norm_data["message_id"]
                    })

            elif path == "/api/v1/control/cloud":
                # Control simulation mode for M2 testing / video demo
                if forwarder_ref and "mock_online" in payload:
                    new_state = bool(payload["mock_online"])
                    forwarder_ref.set_online_state(new_state)
                    self._send_json_response(200, {
                        "status": "success",
                        "mock_online": new_state,
                        "message": f"Cloud connectivity simulation set to: {'ONLINE' if new_state else 'OFFLINE'}"
                    })
                else:
                    self._send_json_response(400, {"status": "error", "message": "Invalid control payload"})

            else:
                self._send_json_response(404, {"error": "Not Found"})

    return TelemetryHTTPHandler


class HTTPServerManager:
    """Wrapper to start and stop HTTP ingestion server."""

    def __init__(self, host, port, db_manager, forwarder_ref=None):
        self.host = host
        self.port = port
        self.db_manager = db_manager
        self.forwarder_ref = forwarder_ref
        self.start_time = datetime.now(timezone.utc)
        self.server = None

    def start(self):
        handler_class = make_request_handler(self.db_manager, self.forwarder_ref, self.start_time)
        self.server = ThreadedHTTPServer((self.host, self.port), handler_class)
        logger.info("HTTP Ingestion REST Server listening on http://%s:%d", self.host, self.port)
        self.server.serve_forever()

    def stop(self):
        if self.server:
            logger.info("Stopping HTTP server...")
            self.server.shutdown()
            self.server.server_close()
            self.server = None

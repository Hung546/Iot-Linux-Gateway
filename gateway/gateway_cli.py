#!/usr/bin/env python3
"""
CLI Management Tool for MYIR MYS-6ULX Gateway.
Allows inspecting database status, registered nodes, recent telemetry,
and controlling simulation parameters.
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gateway.config import load_config
from gateway.database import DatabaseManager


def format_table(headers, rows):
    """Simple terminal table formatter."""
    if not rows:
        return "  (No records found)"
    col_widths = [len(h) for h in headers]
    for row in rows:
        for idx, val in enumerate(row):
            col_widths[idx] = max(col_widths[idx], len(str(val)))

    sep = "+-" + "-+-".join(["-" * w for w in col_widths]) + "-+"
    header_str = "| " + " | ".join([f"{h:<{col_widths[i]}}" for i, h in enumerate(headers)]) + " |"

    lines = [sep, header_str, sep]
    for row in rows:
        row_str = "| " + " | ".join([f"{str(val):<{col_widths[i]}}" for i, val in enumerate(row)]) + " |"
        lines.append(row_str)
    lines.append(sep)
    return "\n".join(lines)


def cmd_status(db_path, config):
    db = DatabaseManager(db_path)
    stats = db.get_stats()
    print("=" * 60)
    print("       MYIR MYS-6ULX GATEWAY STATUS")
    print("=" * 60)
    print(f"Board Model        : {config['gateway']['board_model']}")
    print(f"Gateway ID         : {config['gateway']['id']}")
    print(f"Database Path      : {stats['db_path']}")
    print(f"Database Size      : {stats['db_size_kb']} KB")
    print(f"Total Records      : {stats['total_records']}")
    print(f"Pending (Buffer)   : {stats['pending_records']}")
    print(f"Sent (Delivered)   : {stats['sent_records']}")
    print(f"Active Nodes       : {stats['active_nodes_count']}")
    print("=" * 60)


def cmd_nodes(db_path):
    db = DatabaseManager(db_path)
    nodes = db.get_nodes()
    print("\n--- REGISTERED ESP32 NODES ---")
    headers = ["Node ID", "Total Messages", "Last Seen (UTC)", "Client IP"]
    rows = []
    for n in nodes:
        rows.append([
            n.get("node_id", ""),
            n.get("total_messages", 0),
            n.get("last_seen", ""),
            n.get("last_ip", "") or "local"
        ])
    print(format_table(headers, rows))


def cmd_recent(db_path, limit=10):
    db = DatabaseManager(db_path)
    records = db.get_recent_telemetry(limit)
    print(f"\n--- RECENT TELEMETRY (Last {limit}) ---")
    headers = ["ID", "Msg ID", "Node", "Temp(°C)", "Hum(%)", "PM2.5", "CO2", "Status", "Sent At"]
    rows = []
    for r in records:
        rows.append([
            r.get("id"),
            r.get("message_id"),
            r.get("node_id"),
            r.get("temperature_c") if r.get("temperature_c") is not None else "--",
            r.get("humidity_pct") if r.get("humidity_pct") is not None else "--",
            r.get("pm25_ug_m3") if r.get("pm25_ug_m3") is not None else "--",
            r.get("co2_ppm") if r.get("co2_ppm") is not None else "--",
            r.get("status"),
            r.get("sent_at") or "--"
        ])
    print(format_table(headers, rows))


def cmd_set_cloud(port, online):
    url = f"http://127.0.0.1:{port}/api/v1/control/cloud"
    data = json.dumps({"mock_online": online}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            print(f"Cloud simulation switched: {body.get('message')}")
    except Exception as e:
        print(f"Error communicating with running gateway HTTP server on port {port}: {e}")


def main():
    parser = argparse.ArgumentParser(description="CLI tool to inspect MYIR MYS-6ULX Gateway")
    parser.add_argument("--db", type=str, help="Override SQLite database path")
    parser.add_argument("--port", type=int, help="Override HTTP control port")

    subparsers = parser.add_subparsers(dest="subcommand")
    subparsers.add_parser("status", help="Show gateway and database status")
    subparsers.add_parser("nodes", help="List registered ESP32 nodes")

    recent_p = subparsers.add_parser("recent", help="Show recent telemetry")
    recent_p.add_argument("--limit", "-n", type=int, default=10, help="Number of records to show")

    cloud_p = subparsers.add_parser("cloud", help="Control cloud uplink simulation")
    cloud_p.add_argument("--online", action="store_true", help="Set cloud uplink ONLINE")
    cloud_p.add_argument("--offline", action="store_true", help="Set cloud uplink OFFLINE (buffer in SQLite)")

    args = parser.parse_args()
    config = load_config()

    db_path = args.db if args.db else config["gateway"]["db_path"]
    port = args.port if args.port else config["http_server"]["port"]

    if args.subcommand == "status" or not args.subcommand:
        cmd_status(db_path, config)
    elif args.subcommand == "nodes":
        cmd_nodes(db_path)
    elif args.subcommand == "recent":
        cmd_recent(db_path, args.limit)
    elif args.subcommand == "cloud":
        if args.online:
            cmd_set_cloud(port, True)
        elif args.offline:
            cmd_set_cloud(port, False)
        else:
            print("Specify --online or --offline")


if __name__ == "__main__":
    main()

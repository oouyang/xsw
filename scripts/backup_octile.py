#!/usr/bin/env python3
"""
Backup Octile databases (scores + users) to timestamped JSON and/or SQLite copies.

Usage:
    # In Docker container:
    docker exec xsw-xsw-1 python3 /app/scripts/backup_octile.py

    # Locally:
    python3 scripts/backup_octile.py

    # Custom paths:
    python3 scripts/backup_octile.py --octile-db data/octile.db --main-db data/xsw_cache.db

    # JSON only (no SQLite copy):
    python3 scripts/backup_octile.py --format json

    # SQLite copy only (fast, no row-level export):
    python3 scripts/backup_octile.py --format sqlite

    # Both (default):
    python3 scripts/backup_octile.py --format all

    # Custom output directory:
    python3 scripts/backup_octile.py --out /backups
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

from sqlalchemy import create_engine, text


def get_engine(db_path):
    if not os.path.exists(db_path):
        return None
    return create_engine(f"sqlite:///{db_path}")


def dump_table(engine, table, columns):
    """Dump a table to a list of dicts."""
    cols = ", ".join(columns)
    with engine.connect() as conn:
        try:
            rows = conn.execute(text(f"SELECT {cols} FROM {table}")).fetchall()
        except Exception:
            return []
    return [dict(zip(columns, row)) for row in rows]


def backup_json(octile_db, main_db, out_dir, timestamp):
    """Export all Octile-related data to a JSON file."""
    data = {"exported_at": timestamp, "octile_scores": [], "octile_sync_data": [],
            "users": [], "user_oauth": []}

    # --- Octile DB ---
    engine = get_engine(octile_db)
    if engine:
        data["octile_scores"] = dump_table(engine, "octile_scores", [
            "id", "puzzle_number", "resolve_time", "browser_uuid",
            "timestamp_utc", "os", "browser", "ip", "user_agent",
            "solution", "flagged", "user_id", "display_name",
        ])
        data["octile_sync_data"] = dump_table(engine, "octile_sync_data", [
            "user_id", "coins", "total_solved", "solved_set", "best_times",
            "level_progress", "energy", "streak", "achievements",
            "daily_checkin", "ach_claimed", "updated_at",
        ])
        # Convert datetime objects to strings
        for row in data["octile_scores"]:
            for k, v in row.items():
                if hasattr(v, "isoformat"):
                    row[k] = v.isoformat()
        for row in data["octile_sync_data"]:
            for k, v in row.items():
                if hasattr(v, "isoformat"):
                    row[k] = v.isoformat()
        engine.dispose()
    else:
        print(f"  [WARN] Octile DB not found: {octile_db}")

    # --- Main DB (users only) ---
    engine = get_engine(main_db)
    if engine:
        data["users"] = dump_table(engine, "users", [
            "id", "display_name", "email", "avatar_url", "is_active",
            "created_at", "last_login_at",
        ])
        data["user_oauth"] = dump_table(engine, "user_oauth", [
            "id", "user_id", "provider", "provider_user_id",
            "provider_email", "provider_name", "created_at", "last_used_at",
        ])
        for table_rows in (data["users"], data["user_oauth"]):
            for row in table_rows:
                for k, v in row.items():
                    if hasattr(v, "isoformat"):
                        row[k] = v.isoformat()
        engine.dispose()
    else:
        print(f"  [WARN] Main DB not found: {main_db}")

    # Write JSON
    filename = f"octile_backup_{timestamp}.json"
    filepath = os.path.join(out_dir, filename)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    scores_n = len(data["octile_scores"])
    sync_n = len(data["octile_sync_data"])
    users_n = len(data["users"])
    size = os.path.getsize(filepath)
    print(f"  JSON: {filepath}")
    print(f"    {scores_n} scores, {sync_n} sync records, {users_n} users ({size:,} bytes)")
    return filepath


def backup_sqlite(octile_db, main_db, out_dir, timestamp):
    """Safe SQLite backup using VACUUM INTO (compact, WAL-safe)."""
    copied = []
    for label, src in [("octile", octile_db), ("main", main_db)]:
        if not os.path.exists(src):
            print(f"  [WARN] {label} DB not found: {src}")
            continue
        dest = os.path.join(out_dir, f"octile_backup_{label}_{timestamp}.db")
        try:
            conn = sqlite3.connect(src)
            conn.execute("VACUUM INTO ?", (dest,))
            conn.close()
            size = os.path.getsize(dest)
            print(f"  SQLite ({label}): {dest} ({size:,} bytes)")
            copied.append(dest)
        except Exception as e:
            print(f"  [ERROR] {label} SQLite backup failed: {e}")
            if os.path.exists(dest):
                os.remove(dest)
    return copied


def main():
    parser = argparse.ArgumentParser(
        description="Backup Octile scores, users, and sync data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--octile-db",
        default=os.getenv("OCTILE_DB_PATH", "/app/data/octile.db"),  # matches octile_api.py default
        help="Path to Octile SQLite DB (default: /app/data/octile.db)",
    )
    parser.add_argument(
        "--main-db",
        default=os.getenv("DB_PATH", "/app/data/xsw_cache.db"),
        help="Path to main (xsw) SQLite DB (default: /app/data/xsw_cache.db)",
    )
    parser.add_argument(
        "--out",
        default=os.getenv("BACKUP_DIR", "/app/data/backups"),
        help="Output directory (default: /app/data/backups)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "sqlite", "all"],
        default="all",
        help="Backup format: json, sqlite, or all (default: all)",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Suppress output except errors",
    )

    args = parser.parse_args()

    # Resolve relative paths
    octile_db = os.path.abspath(args.octile_db)
    main_db = os.path.abspath(args.main_db)
    out_dir = os.path.abspath(args.out)

    os.makedirs(out_dir, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if not args.quiet:
        print(f"Octile Backup — {timestamp}")
        print(f"  Octile DB: {octile_db}")
        print(f"  Main DB:   {main_db}")
        print(f"  Output:    {out_dir}")
        print()

    files = []

    if args.format in ("json", "all"):
        files.append(backup_json(octile_db, main_db, out_dir, timestamp))

    if args.format in ("sqlite", "all"):
        files.extend(backup_sqlite(octile_db, main_db, out_dir, timestamp))

    if not args.quiet:
        print()
        print(f"Done. {len(files)} file(s) written to {out_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

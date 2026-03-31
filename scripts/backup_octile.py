#!/usr/bin/env python3
"""
Backup Octile database to timestamped SQLite copy and/or JSON dump.

Usage:
    # In Docker container:
    docker exec xsw-xsw-1 python3 /app/scripts/backup_octile.py

    # Locally:
    python3 scripts/backup_octile.py

    # Custom paths:
    python3 scripts/backup_octile.py --db data/octile.db

    # JSON only:
    python3 scripts/backup_octile.py --format json

    # SQLite copy only (fast, WAL-safe):
    python3 scripts/backup_octile.py --format sqlite

    # Both (default):
    python3 scripts/backup_octile.py --format all
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone


def dump_table(conn, table):
    """Dump all rows from a table as list of dicts. Returns [] if table doesn't exist."""
    try:
        cur = conn.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cur.fetchall()]
        if not columns:
            return []
        cur = conn.execute(f"SELECT * FROM {table}")
        return [dict(zip(columns, row)) for row in cur.fetchall()]
    except Exception:
        return []


def backup_json(db_path, out_dir, timestamp):
    """Export all Octile tables to a JSON file."""
    conn = sqlite3.connect(db_path)

    tables = ["octile_scores", "octile_users", "octile_progress"]
    data = {"exported_at": timestamp, "db_path": db_path}

    total_rows = 0
    for table in tables:
        rows = dump_table(conn, table)
        # Convert any non-serializable values
        for row in rows:
            for k, v in row.items():
                if hasattr(v, "isoformat"):
                    row[k] = v.isoformat()
        data[table] = rows
        total_rows += len(rows)

    conn.close()

    filename = f"octile_backup_{timestamp}.json"
    filepath = os.path.join(out_dir, filename)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    size = os.path.getsize(filepath)
    print(f"  JSON: {filepath}")
    for table in tables:
        print(f"    {table}: {len(data[table])} rows")
    print(f"    Total: {total_rows} rows ({size:,} bytes)")
    return filepath


def backup_sqlite(db_path, out_dir, timestamp):
    """Safe SQLite backup using VACUUM INTO (compact, WAL-safe)."""
    dest = os.path.join(out_dir, f"octile_backup_{timestamp}.db")
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("VACUUM INTO ?", (dest,))
        conn.close()
        size = os.path.getsize(dest)
        print(f"  SQLite: {dest} ({size:,} bytes)")
        return dest
    except Exception as e:
        print(f"  [ERROR] SQLite backup failed: {e}")
        if os.path.exists(dest):
            os.remove(dest)
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Backup Octile database (scores, users, progress)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--db",
        default=os.getenv("OCTILE_DB_PATH", "/app/data/octile.db"),
        help="Path to octile.db (default: /app/data/octile.db)",
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
        help="Backup format (default: all)",
    )

    args = parser.parse_args()
    db_path = os.path.abspath(args.db)
    out_dir = os.path.abspath(args.out)

    if not os.path.exists(db_path):
        print(f"ERROR: Database not found: {db_path}")
        return 1

    os.makedirs(out_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    print(f"Octile Backup — {timestamp}")
    print(f"  Source: {db_path} ({os.path.getsize(db_path):,} bytes)")
    print(f"  Output: {out_dir}")
    print()

    files = []

    if args.format in ("sqlite", "all"):
        result = backup_sqlite(db_path, out_dir, timestamp)
        if result:
            files.append(result)

    if args.format in ("json", "all"):
        files.append(backup_json(db_path, out_dir, timestamp))

    print()
    print(f"Done. {len(files)} file(s) written to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

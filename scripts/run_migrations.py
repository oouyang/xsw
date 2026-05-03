#!/usr/bin/env python3
"""
Run database migrations for Octile backend.

Usage:
    python scripts/run_migrations.py

This script runs all SQL migrations in migrations/ directory in order.
Safe to run multiple times (idempotent).
"""

import sys
import sqlite3
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from octile_api import get_db_path


def run_migrations():
    """Run all migrations in migrations/ directory.

    Uses file-based locking to prevent concurrent migrations in multi-instance deployments.
    """
    db_path = get_db_path()
    migrations_dir = Path(__file__).parent.parent / "migrations"
    lock_file = Path(db_path).parent / ".migration.lock"

    if not migrations_dir.exists():
        print(f"❌ Migrations directory not found: {migrations_dir}")
        return False

    # Acquire lock to prevent concurrent migrations
    import fcntl

    lock_fd = None
    try:
        lock_fd = open(lock_file, "w")
        # Try to acquire exclusive lock (non-blocking)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print("🔒 Migration lock acquired")
    except IOError:
        print("⏳ Another migration is already running. Waiting...")
        # Wait for lock (blocking)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            print("🔒 Migration lock acquired (after wait)")
        except Exception as e:
            print(f"❌ Failed to acquire lock: {e}")
            if lock_fd:
                lock_fd.close()
            return False

    try:
        # Get all .sql files in migrations directory
        migration_files = sorted(migrations_dir.glob("*.sql"))

        if not migration_files:
            print("✅ No migrations to run")
            return True

        print(f"📂 Database: {db_path}")
        print(f"📁 Migrations directory: {migrations_dir}")
        print(f"🔍 Found {len(migration_files)} migration(s)\n")

        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Run each migration
        for migration_file in migration_files:
            print(f"🔧 Running {migration_file.name}...")

            with open(migration_file) as f:
                sql = f.read()

            try:
                # Execute migration (SQLite allows multiple statements in executescript)
                cursor.executescript(sql)
                conn.commit()
                print(f"   ✅ {migration_file.name} completed\n")
            except Exception as e:
                print(f"   ❌ {migration_file.name} failed: {e}\n")
                conn.rollback()
                return False

        # Verify game_scores table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='game_scores'"
        )
        if cursor.fetchone():
            print("✅ Verification: game_scores table exists")

            # Count indexes
            cursor.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND tbl_name='game_scores'"
            )
            index_count = cursor.fetchone()[0]
            print(f"✅ Verification: {index_count} indexes created")
        else:
            print("❌ Verification failed: game_scores table not found")
            return False

        conn.close()
        print("\n🎉 All migrations completed successfully!")
        return True

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False
    finally:
        # Release lock
        if lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
            # Remove lock file (optional, for cleanliness)
            try:
                lock_file.unlink()
            except OSError:
                pass
            print("🔓 Migration lock released")


if __name__ == "__main__":
    success = run_migrations()
    sys.exit(0 if success else 1)

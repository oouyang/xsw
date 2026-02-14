#!/usr/bin/env python3
"""
Drop legacy data from SQLite database.

Removes books and their chapters that have purely numeric IDs
(from the old m.xsw.tw source) which can't be resolved on czbooks.net.

Usage:
    # Dry run (default) — show what would be deleted
    python scripts/drop_legacy_data.py

    # Actually delete
    python scripts/drop_legacy_data.py --confirm

    # Use a specific database file
    python scripts/drop_legacy_data.py --db /app/data/xsw_cache.db --confirm
"""
import argparse
import os
import sys

# Allow importing project modules when run from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text


def main():
    parser = argparse.ArgumentParser(description="Drop legacy numeric-ID data from the SQLite cache")
    parser.add_argument(
        "--db",
        default=os.environ.get("DB_PATH", "xsw_cache.db"),
        help="Path to SQLite database (default: $DB_PATH or xsw_cache.db)",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually delete. Without this flag, only a dry-run report is shown.",
    )
    args = parser.parse_args()

    db_path = args.db
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        sys.exit(1)

    engine = create_engine(f"sqlite:///{db_path}")

    with engine.connect() as conn:
        # Count legacy books (purely numeric IDs)
        legacy_books = conn.execute(
            text("""
                SELECT id, name, author,
                       (SELECT COUNT(*) FROM chapters WHERE chapters.book_id = books.id) AS ch_count
                FROM books
                WHERE CAST(id AS INTEGER) > 0
                  AND CAST(id AS INTEGER) || '' = id
                ORDER BY name
            """)
        ).fetchall()

        total_books = conn.execute(text("SELECT COUNT(*) FROM books")).scalar()
        total_chapters = conn.execute(text("SELECT COUNT(*) FROM chapters")).scalar()

        legacy_chapter_count = 0
        for row in legacy_books:
            legacy_chapter_count += row[3]

        print(f"Database: {db_path}")
        print(f"Total books: {total_books}, Total chapters: {total_chapters}")
        print(f"Legacy books (numeric ID): {len(legacy_books)}, Legacy chapters: {legacy_chapter_count}")
        print()

        if not legacy_books:
            print("No legacy data found. Nothing to do.")
            return

        print("Legacy books to remove:")
        print(f"  {'ID':>10}  {'Chapters':>8}  Name / Author")
        print(f"  {'—'*10}  {'—'*8}  {'—'*40}")
        for row in legacy_books:
            book_id, name, author, ch_count = row
            print(f"  {book_id:>10}  {ch_count:>8}  {name} / {author or '?'}")

        print()

        if not args.confirm:
            print("Dry run — no changes made. Pass --confirm to delete.")
            return

        # Delete chapters first (FK constraint), then books
        deleted_chapters = conn.execute(
            text("""
                DELETE FROM chapters
                WHERE book_id IN (
                    SELECT id FROM books
                    WHERE CAST(id AS INTEGER) > 0
                      AND CAST(id AS INTEGER) || '' = id
                )
            """)
        ).rowcount

        deleted_books = conn.execute(
            text("""
                DELETE FROM books
                WHERE CAST(id AS INTEGER) > 0
                  AND CAST(id AS INTEGER) || '' = id
            """)
        ).rowcount

        conn.commit()

    # VACUUM must run outside a transaction
    with engine.connect() as conn:
        conn.execute(text("VACUUM"))
        conn.commit()

        print(f"Deleted {deleted_books} legacy books and {deleted_chapters} chapters.")

        # Show remaining counts
        remaining_books = conn.execute(text("SELECT COUNT(*) FROM books")).scalar()
        remaining_chapters = conn.execute(text("SELECT COUNT(*) FROM chapters")).scalar()
        print(f"Remaining: {remaining_books} books, {remaining_chapters} chapters")


if __name__ == "__main__":
    main()

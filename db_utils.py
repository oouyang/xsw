# db_utils.py
"""
Database utilities for migration, warmup, and maintenance.
"""
from typing import Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from db_models import Book, Chapter, Category, db_manager


def migrate_from_old_cache(old_cache_data: Dict[str, Any]) -> None:
    """
    Migrate data from old TTL cache format to database.
    Useful for one-time migration if you have existing cached data.
    """
    if not db_manager:
        raise RuntimeError("Database not initialized")

    session = db_manager.get_session()
    try:
        migrated_books = 0
        migrated_chapters = 0

        # Example: migrate books if old cache has them
        if "books" in old_cache_data:
            for book_id, book_data in old_cache_data["books"].items():
                existing = session.query(Book).filter(Book.id == book_id).first()
                if not existing:
                    book = Book(
                        id=book_id,
                        name=book_data.get("name", ""),
                        author=book_data.get("author"),
                        type=book_data.get("type"),
                        status=book_data.get("status"),
                        update=book_data.get("update"),
                    )
                    session.add(book)
                    migrated_books += 1

        # Example: migrate chapters if old cache has them
        if "chapters" in old_cache_data:
            for key, chapter_data in old_cache_data["chapters"].items():
                book_id, chapter_num = key
                existing = (
                    session.query(Chapter)
                    .filter(Chapter.book_id == book_id, Chapter.chapter_num == chapter_num)
                    .first()
                )
                if not existing:
                    chapter = Chapter(
                        book_id=book_id,
                        chapter_num=chapter_num,
                        title=chapter_data.get("title"),
                        url=chapter_data.get("url"),
                        text=chapter_data.get("text"),
                    )
                    session.add(chapter)
                    migrated_chapters += 1

        session.commit()
        print(f"[Migration] Migrated {migrated_books} books, {migrated_chapters} chapters")
    except Exception as e:
        session.rollback()
        print(f"[Migration] Error: {e}")
        raise
    finally:
        session.close()


def cleanup_stale_data(days: int = 30) -> Dict[str, int]:
    """
    Remove chapters that haven't been updated in X days.
    Useful for cleaning up old content that might be outdated.
    """
    if not db_manager:
        raise RuntimeError("Database not initialized")

    session = db_manager.get_session()
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Find stale chapters
        stale_chapters = (
            session.query(Chapter)
            .filter(Chapter.updated_at < cutoff_date)
            .all()
        )

        deleted_count = len(stale_chapters)
        for chapter in stale_chapters:
            session.delete(chapter)

        session.commit()
        print(f"[Cleanup] Removed {deleted_count} chapters older than {days} days")

        return {"deleted_chapters": deleted_count, "cutoff_days": days}
    except Exception as e:
        session.rollback()
        print(f"[Cleanup] Error: {e}")
        raise
    finally:
        session.close()


def get_database_stats() -> Dict[str, Any]:
    """Get detailed database statistics."""
    if not db_manager:
        raise RuntimeError("Database not initialized")

    session = db_manager.get_session()
    try:
        stats = {
            "total_books": session.query(Book).count(),
            "total_chapters": session.query(Chapter).count(),
            "chapters_with_content": session.query(Chapter)
            .filter(Chapter.text.isnot(None))
            .count(),
            "chapters_without_content": session.query(Chapter)
            .filter(Chapter.text.is_(None))
            .count(),
            "total_categories": session.query(Category).count(),
        }

        # Recent activity
        recent_cutoff = datetime.utcnow() - timedelta(hours=24)
        stats["books_scraped_24h"] = (
            session.query(Book)
            .filter(Book.last_scraped_at >= recent_cutoff)
            .count()
        )
        stats["chapters_fetched_24h"] = (
            session.query(Chapter)
            .filter(Chapter.fetched_at >= recent_cutoff)
            .count()
        )

        # Top authors by book count
        from sqlalchemy import func

        top_authors = (
            session.query(Book.author, func.count(Book.id).label("count"))
            .group_by(Book.author)
            .order_by(func.count(Book.id).desc())
            .limit(5)
            .all()
        )
        stats["top_authors"] = [
            {"author": author, "book_count": count}
            for author, count in top_authors
            if author
        ]

        return stats
    finally:
        session.close()


def vacuum_database() -> None:
    """
    Optimize SQLite database by running VACUUM.
    This rebuilds the database file, reclaiming unused space.
    """
    if not db_manager:
        raise RuntimeError("Database not initialized")

    with db_manager.engine.connect() as conn:
        conn.execute("VACUUM")
        print("[Maintenance] Database vacuumed successfully")


def export_book_to_json(book_id: str, include_content: bool = True) -> Dict[str, Any]:
    """
    Export a single book with all its chapters to JSON format.
    Useful for backup or analysis.
    """
    if not db_manager:
        raise RuntimeError("Database not initialized")

    session = db_manager.get_session()
    try:
        book = session.query(Book).filter(Book.id == book_id).first()
        if not book:
            return {"error": "Book not found"}

        chapters = (
            session.query(Chapter)
            .filter(Chapter.book_id == book_id)
            .order_by(Chapter.chapter_num)
            .all()
        )

        book_data = {
            "id": book.id,
            "name": book.name,
            "author": book.author,
            "type": book.type,
            "status": book.status,
            "update": book.update,
            "last_chapter_num": book.last_chapter_num,
            "created_at": book.created_at.isoformat() if book.created_at else None,
            "last_scraped_at": book.last_scraped_at.isoformat()
            if book.last_scraped_at
            else None,
            "chapters": [],
        }

        for chapter in chapters:
            chapter_data = {
                "number": chapter.chapter_num,
                "title": chapter.title,
                "url": chapter.url,
                "word_count": chapter.word_count,
            }
            if include_content:
                chapter_data["text"] = chapter.text

            book_data["chapters"].append(chapter_data)

        return book_data
    finally:
        session.close()


if __name__ == "__main__":
    # Example: Run database utilities from command line
    import sys
    from db_models import init_database

    if len(sys.argv) < 2:
        print("Usage: python db_utils.py [command]")
        print("Commands: stats, cleanup, vacuum")
        sys.exit(1)

    # Initialize database
    init_database()

    command = sys.argv[1]

    if command == "stats":
        stats = get_database_stats()
        print("\n=== Database Statistics ===")
        for key, value in stats.items():
            print(f"{key}: {value}")

    elif command == "cleanup":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        result = cleanup_stale_data(days)
        print(f"Cleaned up {result['deleted_chapters']} chapters")

    elif command == "vacuum":
        vacuum_database()
        print("Database optimized")

    else:
        print(f"Unknown command: {command}")

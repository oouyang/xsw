# cache_manager.py
"""
Hybrid cache manager: Database-first with in-memory TTL cache.
Strategy: Check memory → Check DB → Fetch from web → Store to DB → Cache in memory
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
import time
import threading
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

import uuid

import db_models
from db_models import Book, Chapter
from pydantic import BaseModel


def generate_public_id() -> str:
    """Generate a short random ID for public URLs."""
    return uuid.uuid4().hex[:8]


# Pydantic models for API responses
class BookInfo(BaseModel):
    name: str
    author: str
    type: str
    status: str
    update: str
    last_chapter_title: str
    last_chapter_url: str
    last_chapter_number: Optional[int] = None
    book_id: Optional[str] = None
    public_id: Optional[str] = None


class ChapterRef(BaseModel):
    number: int
    title: str
    url: str
    id: Optional[str] = None  # chapter public_id


class ChapterContent(BaseModel):
    book_id: Optional[str] = None
    chapter_num: Optional[int] = None
    title: Optional[str] = None
    url: str
    text: str
    chapter_id: Optional[str] = None  # chapter public_id


# Simple TTL Cache for in-memory caching
class TTLCache:
    """Thread-safe TTL cache with LRU eviction."""

    def __init__(self, ttl_seconds: int, max_items: int):
        self.ttl = ttl_seconds
        self.max_items = max_items
        self._store: Dict[Any, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: Any) -> Optional[Any]:
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            ts, value = entry
            if now - ts > self.ttl:
                # expired
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: Any, value: Any) -> None:
        now = time.time()
        with self._lock:
            # Evict if full
            if len(self._store) >= self.max_items:
                # remove oldest by timestamp
                oldest_key = min(self._store.items(), key=lambda kv: kv[1][0])[0]
                self._store.pop(oldest_key, None)
            self._store[key] = (now, value)

    def invalidate(self, key: Any) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


class CacheManager:
    """
    Hybrid cache manager: Database-first with in-memory TTL cache.

    Cache hierarchy:
    1. Memory (TTL cache) - fastest, volatile
    2. Database (SQLite) - persistent, slower than memory
    3. Web scraping - slowest, fallback
    """

    def __init__(self, ttl_seconds: int = 900, max_memory_items: int = 500):
        self.ttl_seconds = ttl_seconds
        self.memory_cache = TTLCache(ttl_seconds, max_memory_items)
        print(f"[Cache] Initialized with TTL={ttl_seconds}s, max_items={max_memory_items}")

    def _get_session(self) -> Session:
        """Get database session."""
        return db_models.db_manager.get_session()

    # ===== Book Info Methods =====

    def get_book_info(self, book_id: str) -> Optional[BookInfo]:
        """Get book info from cache hierarchy: memory → DB → None."""
        # Check memory cache
        cache_key = f"book:{book_id}"
        cached = self.memory_cache.get(cache_key)
        if cached:
            return cached

        # Check database
        session = self._get_session()
        try:
            book = session.query(Book).filter(Book.id == book_id).first()
            if book:
                book_info = BookInfo(
                    name=book.name,
                    author=book.author or "",
                    type=book.type or "",
                    status=book.status or "",
                    update=book.update or "",
                    last_chapter_title=book.last_chapter_title or "",
                    last_chapter_url=book.last_chapter_url or "",
                    last_chapter_number=book.last_chapter_num,
                    book_id=book.id,
                    public_id=book.public_id,
                )
                # Cache in memory
                self.memory_cache.set(cache_key, book_info)
                return book_info
        except SQLAlchemyError as e:
            print(f"[Cache] DB error getting book {book_id}: {e}")
        finally:
            session.close()

        return None

    def store_book_info(self, book_id: str, info: Dict[str, Any]) -> None:
        """Store book info to database and memory cache."""
        session = self._get_session()
        try:
            # Check if book exists
            book = session.query(Book).filter(Book.id == book_id).first()

            if book:
                # Update existing
                book.name = info.get("name", book.name)
                book.author = info.get("author", book.author)
                book.type = info.get("type", book.type)
                book.status = info.get("status", book.status)
                book.update = info.get("update", book.update)
                book.last_chapter_title = info.get("last_chapter_title", book.last_chapter_title)
                book.last_chapter_url = info.get("last_chapter_url", book.last_chapter_url)
                book.last_chapter_num = info.get("last_chapter_number", book.last_chapter_num)
                book.last_scraped_at = datetime.utcnow()
                # Assign public_id if not set
                if not book.public_id:
                    book.public_id = generate_public_id()
            else:
                # Create new
                book = Book(
                    id=book_id,
                    public_id=generate_public_id(),
                    name=info.get("name", ""),
                    author=info.get("author"),
                    type=info.get("type"),
                    status=info.get("status"),
                    update=info.get("update"),
                    last_chapter_title=info.get("last_chapter_title"),
                    last_chapter_url=info.get("last_chapter_url"),
                    last_chapter_num=info.get("last_chapter_number"),
                    source_url=info.get("source_url"),
                )
                session.add(book)

            session.commit()

            # Cache in memory - merge book_id and public_id into info dict
            info_with_id = {**info, "book_id": book_id, "public_id": book.public_id}
            book_info = BookInfo(**info_with_id)
            cache_key = f"book:{book_id}"
            self.memory_cache.set(cache_key, book_info)

            print(f"[Cache] Stored book {book_id} to DB and memory")
        except SQLAlchemyError as e:
            try:
                session.rollback()
            except Exception:
                pass  # Ignore rollback errors when no transaction is active
            print(f"[Cache] Error storing book {book_id}: {e}")
        finally:
            session.close()

    # ===== Chapter Methods =====

    def get_chapter_content(
        self, book_id: str, chapter_num: int
    ) -> Optional[ChapterContent]:
        """Get chapter content from cache hierarchy: memory → DB → None."""
        # Check memory cache
        cache_key = f"chapter:{book_id}:{chapter_num}"
        cached = self.memory_cache.get(cache_key)
        if cached:
            return cached

        # Check database
        session = self._get_session()
        try:
            chapter = (
                session.query(Chapter)
                .filter(Chapter.book_id == book_id, Chapter.chapter_num == chapter_num)
                .first()
            )
            if chapter and chapter.text:
                content = ChapterContent(
                    book_id=chapter.book_id,
                    chapter_num=chapter.chapter_num,
                    title=chapter.title,
                    url=chapter.url,
                    text=chapter.text,
                    chapter_id=chapter.public_id,
                )
                # Cache in memory
                self.memory_cache.set(cache_key, content)
                return content
        except SQLAlchemyError as e:
            print(f"[Cache] DB error getting chapter {book_id}:{chapter_num}: {e}")
        finally:
            session.close()

        return None

    def store_chapter_content(
        self, book_id: str, chapter_num: int, content_data: Dict[str, Any]
    ) -> None:
        """Store chapter content to database and memory cache."""
        session = self._get_session()
        try:
            # Check if chapter exists
            chapter = (
                session.query(Chapter)
                .filter(Chapter.book_id == book_id, Chapter.chapter_num == chapter_num)
                .first()
            )

            text = content_data.get("text", "")
            word_count = len(text) if text else 0

            if chapter:
                # Update existing
                chapter.title = content_data.get("title", chapter.title)
                chapter.url = content_data.get("url", chapter.url)
                chapter.text = text
                chapter.word_count = word_count
                chapter.updated_at = datetime.utcnow()
                # Assign public_id if not set
                if not chapter.public_id:
                    chapter.public_id = generate_public_id()
            else:
                # Create new
                chapter = Chapter(
                    book_id=book_id,
                    chapter_num=chapter_num,
                    public_id=generate_public_id(),
                    title=content_data.get("title"),
                    url=content_data.get("url", ""),
                    text=text,
                    word_count=word_count,
                )
                session.add(chapter)

            session.commit()

            # Cache in memory
            content = ChapterContent(
                book_id=book_id,
                chapter_num=chapter_num,
                title=content_data.get("title"),
                url=content_data.get("url", ""),
                text=text,
                chapter_id=chapter.public_id,
            )
            cache_key = f"chapter:{book_id}:{chapter_num}"
            self.memory_cache.set(cache_key, content)

            print(f"[Cache] Stored chapter {book_id}:{chapter_num} to DB and memory")
        except SQLAlchemyError as e:
            try:
                session.rollback()
            except Exception:
                pass  # Ignore rollback errors when no transaction is active
            print(f"[Cache] Error storing chapter {book_id}:{chapter_num}: {e}")
        finally:
            session.close()

    def get_chapter_list(self, book_id: str) -> Optional[List[ChapterRef]]:
        """Get full chapter list for a book from DB."""
        session = self._get_session()
        try:
            chapters = (
                session.query(Chapter)
                .filter(Chapter.book_id == book_id)
                .order_by(Chapter.chapter_num)
                .all()
            )
            if chapters:
                return [
                    ChapterRef(number=c.chapter_num, title=c.title or "", url=c.url, id=c.public_id)
                    for c in chapters
                ]
        except SQLAlchemyError as e:
            print(f"[Cache] DB error getting chapter list {book_id}: {e}")
        finally:
            session.close()
        return None

    def store_chapter_refs(self, book_id: str, chapters: List[Dict[str, Any]]) -> None:
        """Store chapter references (metadata only, no content) to database."""
        session = self._get_session()
        stored_count = 0
        updated_count = 0
        skipped_count = 0
        batch_size = 100  # Commit every 100 chapters for better performance
        pending_commit = False

        try:
            for idx, ch_data in enumerate(chapters):
                chapter_num = ch_data.get("number")
                if chapter_num is None:
                    skipped_count += 1
                    continue

                try:
                    # Check if exists
                    chapter = (
                        session.query(Chapter)
                        .filter(Chapter.book_id == book_id, Chapter.chapter_num == chapter_num)
                        .first()
                    )

                    if chapter:
                        # Update metadata only (don't overwrite text if it exists)
                        chapter.title = ch_data.get("title", chapter.title)
                        chapter.url = ch_data.get("url", chapter.url)
                        # Assign public_id if not set
                        if not chapter.public_id:
                            chapter.public_id = generate_public_id()
                        updated_count += 1
                        pending_commit = True
                    else:
                        # Create new (no text yet)
                        chapter = Chapter(
                            book_id=book_id,
                            chapter_num=chapter_num,
                            public_id=generate_public_id(),
                            title=ch_data.get("title"),
                            url=ch_data.get("url", ""),
                            text=None,  # Will be filled when content is fetched
                        )
                        session.add(chapter)
                        stored_count += 1
                        pending_commit = True

                except SQLAlchemyError as e:
                    print(f"[Cache] Warning: Failed to prepare chapter {book_id}:{chapter_num}: {e}")
                    skipped_count += 1
                    continue

                # Batch commit every N chapters or at the end
                if pending_commit and ((idx + 1) % batch_size == 0 or (idx + 1) == len(chapters)):
                    try:
                        session.commit()
                        pending_commit = False
                    except IntegrityError:
                        # Another thread already stored these chapters — not an error
                        session.rollback()
                        pending_commit = False
                        print(f"[Cache] Batch at chapter {idx + 1} already exists (concurrent write), skipping")
                    except SQLAlchemyError as e:
                        try:
                            session.rollback()
                        except Exception:
                            pass
                        print(f"[Cache] Warning: Failed to commit batch at chapter {idx + 1}: {e}")

            print(f"[Cache] Stored {stored_count} new, updated {updated_count}, skipped {skipped_count} chapter refs for book {book_id}")
        except Exception as e:
            print(f"[Cache] Error storing chapter refs for book {book_id}: {e}")
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()

    # ===== Utility Methods =====

    def invalidate_book(self, book_id: str) -> None:
        """Invalidate all cache entries for a book (memory only, DB remains)."""
        self.memory_cache.invalidate(f"book:{book_id}")
        # Also invalidate chapter memory cache (DB remains as source of truth)
        print(f"[Cache] Invalidated memory cache for book {book_id}")

    def delete_book_chapters(self, book_id: str) -> int:
        """Delete all chapter records for a book from database."""
        session = self._get_session()
        try:
            deleted_count = session.query(Chapter).filter(Chapter.book_id == book_id).delete()
            session.commit()
            # Also clear memory cache
            self.memory_cache.invalidate(f"book:{book_id}")
            print(f"[Cache] Deleted {deleted_count} chapters from DB for book {book_id}")
            return deleted_count
        except SQLAlchemyError as e:
            try:
                session.rollback()
            except Exception:
                pass
            print(f"[Cache] Error deleting chapters for book {book_id}: {e}")
            return 0
        finally:
            session.close()

    def clear_memory_cache(self) -> None:
        """Clear all in-memory cache."""
        self.memory_cache.clear()
        print("[Cache] Cleared all memory cache")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        session = self._get_session()
        try:
            book_count = session.query(Book).count()
            chapter_count = session.query(Chapter).count()
            chapters_with_content = session.query(Chapter).filter(Chapter.text.isnot(None)).count()

            return {
                "books_in_db": book_count,
                "chapters_in_db": chapter_count,
                "chapters_with_content": chapters_with_content,
                "memory_cache_size": len(self.memory_cache._store),
                "memory_cache_ttl": self.ttl_seconds,
            }
        finally:
            session.close()


# Global cache manager instance
cache_manager: Optional[CacheManager] = None


def init_cache_manager(ttl_seconds: int = 900, max_memory_items: int = 500) -> CacheManager:
    """Initialize the cache manager."""
    global cache_manager
    cache_manager = CacheManager(ttl_seconds, max_memory_items)
    return cache_manager

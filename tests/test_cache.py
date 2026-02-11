"""Tests for cache_manager.py — TTLCache and CacheManager with in-memory SQLite."""
import time

from cache_manager import TTLCache


# ===== TTLCache =====

class TestTTLCache:
    def test_set_get(self):
        cache = TTLCache(ttl_seconds=60, max_items=10)
        cache.set("k1", "v1")
        assert cache.get("k1") == "v1"

    def test_expiry(self):
        cache = TTLCache(ttl_seconds=1, max_items=10)
        cache.set("k1", "v1")
        assert cache.get("k1") == "v1"
        time.sleep(1.2)
        assert cache.get("k1") is None

    def test_lru_eviction(self):
        cache = TTLCache(ttl_seconds=60, max_items=2)
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        cache.set("k3", "v3")  # should evict k1 (oldest)
        assert cache.get("k1") is None
        assert cache.get("k2") == "v2"
        assert cache.get("k3") == "v3"

    def test_invalidate(self):
        cache = TTLCache(ttl_seconds=60, max_items=10)
        cache.set("k1", "v1")
        cache.invalidate("k1")
        assert cache.get("k1") is None

    def test_clear(self):
        cache = TTLCache(ttl_seconds=60, max_items=10)
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        cache.clear()
        assert cache.get("k1") is None
        assert cache.get("k2") is None


# ===== CacheManager =====

class TestCacheManagerBookInfo:
    def test_store_and_get(self, cache_mgr_fixture):
        mgr = cache_mgr_fixture
        info = {
            "name": "Test Book",
            "author": "Author",
            "type": "Fantasy",
            "status": "連載中",
            "update": "2026-01-01",
            "last_chapter_title": "Ch 10",
            "last_chapter_url": "https://czbooks.net/n/test/ch10",
            "last_chapter_number": 10,
        }
        mgr.store_book_info("test1", info)
        result = mgr.get_book_info("test1")
        assert result is not None
        assert result.name == "Test Book"
        assert result.author == "Author"
        assert result.book_id == "test1"

    def test_cache_miss(self, cache_mgr_fixture):
        assert cache_mgr_fixture.get_book_info("nonexistent") is None

    def test_update_existing(self, cache_mgr_fixture):
        mgr = cache_mgr_fixture
        info = {
            "name": "Original",
            "author": "A",
            "type": "",
            "status": "",
            "update": "",
            "last_chapter_title": "",
            "last_chapter_url": "",
            "last_chapter_number": 1,
        }
        mgr.store_book_info("test1", info)

        updated = {**info, "name": "Updated", "last_chapter_number": 50}
        mgr.store_book_info("test1", updated)

        result = mgr.get_book_info("test1")
        assert result.name == "Updated"
        assert result.last_chapter_number == 50


class TestCacheManagerChapters:
    def test_store_and_get_content(self, cache_mgr_fixture):
        mgr = cache_mgr_fixture
        # Need a book record first (foreign key)
        mgr.store_book_info("bk1", {
            "name": "B", "author": "A", "type": "", "status": "",
            "update": "", "last_chapter_title": "", "last_chapter_url": "",
            "last_chapter_number": 1,
        })
        content = {"title": "Ch 1", "url": "https://x.com/1", "text": "Hello world"}
        mgr.store_chapter_content("bk1", 1, content)
        result = mgr.get_chapter_content("bk1", 1)
        assert result is not None
        assert result.text == "Hello world"
        assert result.title == "Ch 1"

    def test_content_miss(self, cache_mgr_fixture):
        assert cache_mgr_fixture.get_chapter_content("bk1", 999) is None

    def test_store_and_get_chapter_list(self, cache_mgr_fixture):
        mgr = cache_mgr_fixture
        mgr.store_book_info("bk1", {
            "name": "B", "author": "A", "type": "", "status": "",
            "update": "", "last_chapter_title": "", "last_chapter_url": "",
            "last_chapter_number": 2,
        })
        refs = [
            {"number": 1, "title": "Ch 1", "url": "https://x.com/1"},
            {"number": 2, "title": "Ch 2", "url": "https://x.com/2"},
        ]
        mgr.store_chapter_refs("bk1", refs)
        result = mgr.get_chapter_list("bk1")
        assert result is not None
        assert len(result) == 2
        assert result[0].number == 1
        assert result[1].number == 2

    def test_chapter_list_empty(self, cache_mgr_fixture):
        assert cache_mgr_fixture.get_chapter_list("nonexistent") is None


class TestCacheManagerUtility:
    def _seed_book(self, mgr):
        mgr.store_book_info("bk1", {
            "name": "B", "author": "A", "type": "", "status": "",
            "update": "", "last_chapter_title": "", "last_chapter_url": "",
            "last_chapter_number": 1,
        })

    def test_invalidate_book(self, cache_mgr_fixture):
        mgr = cache_mgr_fixture
        self._seed_book(mgr)
        # Ensure it's in memory cache
        assert mgr.get_book_info("bk1") is not None
        # Invalidate memory only
        mgr.invalidate_book("bk1")
        # Memory miss, but DB still has it → should reload from DB
        assert mgr.get_book_info("bk1") is not None

    def test_delete_book_chapters(self, cache_mgr_fixture):
        mgr = cache_mgr_fixture
        self._seed_book(mgr)
        mgr.store_chapter_refs("bk1", [
            {"number": 1, "title": "Ch 1", "url": "https://x.com/1"},
        ])
        deleted = mgr.delete_book_chapters("bk1")
        assert deleted == 1
        assert mgr.get_chapter_list("bk1") is None

    def test_clear_memory_cache(self, cache_mgr_fixture):
        mgr = cache_mgr_fixture
        self._seed_book(mgr)
        mgr.clear_memory_cache()
        # Memory cleared, but DB still has data
        assert mgr.memory_cache.get("book:bk1") is None
        # DB lookup should still work
        assert mgr.get_book_info("bk1") is not None

    def test_get_stats(self, cache_mgr_fixture):
        mgr = cache_mgr_fixture
        self._seed_book(mgr)
        stats = mgr.get_stats()
        assert "books_in_db" in stats
        assert stats["books_in_db"] >= 1
        assert "chapters_in_db" in stats
        assert "memory_cache_size" in stats

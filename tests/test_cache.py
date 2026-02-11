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


class TestCacheManagerBookInfoNewFields:
    """Tests for description, bookmark_count, view_count fields."""

    def _base_info(self, **overrides):
        base = {
            "name": "Book", "author": "Author", "type": "Fantasy",
            "status": "連載中", "update": "2026-01-01",
            "last_chapter_title": "Ch 1", "last_chapter_url": "https://x.com/1",
            "last_chapter_number": 1,
        }
        base.update(overrides)
        return base

    def test_store_and_get_with_new_fields(self, cache_mgr_fixture):
        mgr = cache_mgr_fixture
        info = self._base_info(
            description="A great novel.",
            bookmark_count=5678,
            view_count=123456,
        )
        mgr.store_book_info("bk_new", info)
        result = mgr.get_book_info("bk_new")
        assert result is not None
        assert result.description == "A great novel."
        assert result.bookmark_count == 5678
        assert result.view_count == 123456

    def test_new_fields_default_none(self, cache_mgr_fixture):
        """When not provided, new fields should be None."""
        mgr = cache_mgr_fixture
        info = self._base_info()  # no description/bookmark/view
        mgr.store_book_info("bk_defaults", info)
        result = mgr.get_book_info("bk_defaults")
        assert result is not None
        assert result.description is None
        assert result.bookmark_count is None
        assert result.view_count is None

    def test_update_preserves_counts_when_not_provided(self, cache_mgr_fixture):
        """Updating without counts should not overwrite existing counts."""
        mgr = cache_mgr_fixture
        info = self._base_info(bookmark_count=100, view_count=200)
        mgr.store_book_info("bk_preserve", info)

        # Update without counts
        update = self._base_info(name="Updated Name")
        mgr.store_book_info("bk_preserve", update)

        result = mgr.get_book_info("bk_preserve")
        assert result.name == "Updated Name"
        assert result.bookmark_count == 100  # preserved
        assert result.view_count == 200  # preserved

    def test_update_overwrites_counts_when_provided(self, cache_mgr_fixture):
        """Updating with new counts should overwrite old ones."""
        mgr = cache_mgr_fixture
        info = self._base_info(bookmark_count=100, view_count=200)
        mgr.store_book_info("bk_overwrite", info)

        update = self._base_info(bookmark_count=999, view_count=888)
        mgr.store_book_info("bk_overwrite", update)

        result = mgr.get_book_info("bk_overwrite")
        assert result.bookmark_count == 999
        assert result.view_count == 888

    def test_description_update(self, cache_mgr_fixture):
        """Description can be updated."""
        mgr = cache_mgr_fixture
        info = self._base_info(description="Original description")
        mgr.store_book_info("bk_desc", info)

        update = self._base_info(description="Updated description")
        mgr.store_book_info("bk_desc", update)

        result = mgr.get_book_info("bk_desc")
        assert result.description == "Updated description"

    def test_round_trip_via_memory_cache(self, cache_mgr_fixture):
        """New fields survive memory cache round-trip (not just DB)."""
        mgr = cache_mgr_fixture
        info = self._base_info(
            description="Desc", bookmark_count=42, view_count=7777
        )
        mgr.store_book_info("bk_mem", info)

        # First call populates memory cache during store
        result1 = mgr.get_book_info("bk_mem")
        assert result1 is not None
        assert result1.description == "Desc"
        assert result1.bookmark_count == 42
        assert result1.view_count == 7777

        # Second call should hit memory cache
        result2 = mgr.get_book_info("bk_mem")
        assert result2.description == "Desc"
        assert result2.bookmark_count == 42

    def test_invalidate_and_reload_from_db(self, cache_mgr_fixture):
        """After memory invalidation, new fields reload from DB."""
        mgr = cache_mgr_fixture
        info = self._base_info(
            description="Persisted", bookmark_count=10, view_count=20
        )
        mgr.store_book_info("bk_inv", info)
        mgr.invalidate_book("bk_inv")

        # Should reload from DB
        result = mgr.get_book_info("bk_inv")
        assert result is not None
        assert result.description == "Persisted"
        assert result.bookmark_count == 10
        assert result.view_count == 20


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

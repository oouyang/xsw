"""API endpoint integration tests via FastAPI TestClient."""
from html_fixtures import (
    CZBOOKS_HOMEPAGE_HTML,
    CZBOOKS_CATEGORY_PAGE_HTML,
    CZBOOKS_BOOK_DETAIL_HTML,
    CZBOOKS_CHAPTER_DETAIL_HTML,
)

BASE = "/xsw/api"


class TestHealth:
    def test_health(self, client):
        resp = client.get(f"{BASE}/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["base_url"] == "https://czbooks.net"


class TestCategories:
    def test_categories(self, client, mock_fetch):
        mock_fetch.register("https://czbooks.net/", CZBOOKS_HOMEPAGE_HTML)
        resp = client.get(f"{BASE}/categories")
        assert resp.status_code == 200
        cats = resp.json()
        assert len(cats) == 2  # xuanhuan deduped
        for c in cats:
            assert "id" in c
            assert "name" in c
            assert "url" in c

    def test_categories_books(self, client, mock_fetch):
        mock_fetch.register(
            "https://czbooks.net/c/fantasy", CZBOOKS_CATEGORY_PAGE_HTML
        )
        resp = client.get(f"{BASE}/categories/fantasy/books")
        assert resp.status_code == 200
        books = resp.json()
        assert len(books) == 2
        assert books[0]["bookname"] == "第一本書"
        assert books[0]["author"] == "作者一"
        assert books[0]["book_id"] == "book1"
        assert books[1]["book_id"] == "book2"

    def test_categories_books_include_counts(self, client, mock_fetch):
        mock_fetch.register(
            "https://czbooks.net/c/fantasy", CZBOOKS_CATEGORY_PAGE_HTML
        )
        resp = client.get(f"{BASE}/categories/fantasy/books")
        assert resp.status_code == 200
        books = resp.json()
        assert books[0]["bookmark_count"] == 1234
        assert books[0]["view_count"] == 56789
        assert books[1]["bookmark_count"] == 999
        assert books[1]["view_count"] == 42000


class TestBookInfo:
    def test_get_book_info(self, client, mock_fetch):
        mock_fetch.register(
            "https://czbooks.net/n/testbook", CZBOOKS_BOOK_DETAIL_HTML
        )
        resp = client.get(f"{BASE}/books/testbook")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "測試小說"
        assert data["author"] == "測試作者"
        assert data["type"] == "玄幻"
        assert data["status"] == "連載中"
        assert data["book_id"] == "testbook"

    def test_get_book_info_includes_description(self, client, mock_fetch):
        mock_fetch.register(
            "https://czbooks.net/n/testbook", CZBOOKS_BOOK_DETAIL_HTML
        )
        resp = client.get(f"{BASE}/books/testbook")
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "這是一本測試小說。"

    def test_get_book_info_includes_counts(self, client, mock_fetch):
        mock_fetch.register(
            "https://czbooks.net/n/testbook", CZBOOKS_BOOK_DETAIL_HTML
        )
        resp = client.get(f"{BASE}/books/testbook")
        assert resp.status_code == 200
        data = resp.json()
        assert data["bookmark_count"] == 5678
        assert data["view_count"] == 123456

    def test_get_book_info_cached(self, client, mock_fetch):
        mock_fetch.register(
            "https://czbooks.net/n/testbook", CZBOOKS_BOOK_DETAIL_HTML
        )
        resp1 = client.get(f"{BASE}/books/testbook")
        assert resp1.status_code == 200
        resp2 = client.get(f"{BASE}/books/testbook")
        assert resp2.status_code == 200
        # fetch_html should have been called only once
        assert len(mock_fetch.call_log) == 1

    def test_get_book_info_cached_preserves_new_fields(self, client, mock_fetch):
        """New fields should survive the cache round-trip."""
        mock_fetch.register(
            "https://czbooks.net/n/testbook", CZBOOKS_BOOK_DETAIL_HTML
        )
        client.get(f"{BASE}/books/testbook")  # populate cache
        resp = client.get(f"{BASE}/books/testbook")  # cache hit
        data = resp.json()
        assert data["description"] == "這是一本測試小說。"
        assert data["bookmark_count"] == 5678
        assert data["view_count"] == 123456


class TestChapters:
    def test_get_chapters_all(self, client, mock_fetch):
        mock_fetch.register(
            "https://czbooks.net/n/testbook", CZBOOKS_BOOK_DETAIL_HTML
        )
        resp = client.get(f"{BASE}/books/testbook/chapters?all=true")
        assert resp.status_code == 200
        data = resp.json()
        # Response may be a dict with volumes or a flat list
        chapters = data["chapters"] if isinstance(data, dict) else data
        assert len(chapters) == 3
        numbers = [ch["number"] for ch in chapters]
        assert numbers == [1, 2, 3]

    def test_get_chapters_paginated(self, client, mock_fetch):
        mock_fetch.register(
            "https://czbooks.net/n/testbook", CZBOOKS_BOOK_DETAIL_HTML
        )
        resp = client.get(f"{BASE}/books/testbook/chapters?page=1")
        assert resp.status_code == 200
        chapters = resp.json()
        assert len(chapters) > 0

    def test_get_chapter_content(self, client, mock_fetch):
        mock_fetch.register(
            "https://czbooks.net/n/testbook", CZBOOKS_BOOK_DETAIL_HTML
        )
        mock_fetch.register(
            "https://czbooks.net/n/testbook/ch1", CZBOOKS_CHAPTER_DETAIL_HTML
        )
        resp = client.get(f"{BASE}/books/testbook/chapters/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "第1章 開始"
        assert "故事從這裡開始" in data["text"]

    def test_get_chapter_not_found(self, client, mock_fetch):
        mock_fetch.register(
            "https://czbooks.net/n/testbook", CZBOOKS_BOOK_DETAIL_HTML
        )
        resp = client.get(f"{BASE}/books/testbook/chapters/999")
        assert resp.status_code == 404
        assert "999" in resp.json()["detail"]


class TestChapterFetchStoresBookInfo:
    """fetch_all_chapters_from_pagination now also stores book info."""

    def test_chapter_fetch_stores_book_info(self, client, mock_fetch):
        """Fetching chapters should also store description and counts."""
        mock_fetch.register(
            "https://czbooks.net/n/testbook", CZBOOKS_BOOK_DETAIL_HTML
        )
        # Fetch chapters (triggers fetch_all_chapters_from_pagination)
        resp = client.get(f"{BASE}/books/testbook/chapters?all=true")
        assert resp.status_code == 200

        # Now book info should be populated from the same HTML
        resp2 = client.get(f"{BASE}/books/testbook")
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["name"] == "測試小說"
        assert data["description"] == "這是一本測試小說。"
        assert data["bookmark_count"] == 5678
        assert data["view_count"] == 123456
        # Should not have made a second fetch — book info was stored during chapter fetch
        assert len(mock_fetch.call_log) == 1

    def test_chapter_fetch_stores_last_chapter(self, client, mock_fetch):
        """Chapter fetch should set last_chapter_number from actual chapters."""
        mock_fetch.register(
            "https://czbooks.net/n/testbook", CZBOOKS_BOOK_DETAIL_HTML
        )
        client.get(f"{BASE}/books/testbook/chapters?all=true")
        resp = client.get(f"{BASE}/books/testbook")
        data = resp.json()
        assert data["last_chapter_number"] == 3
        assert data["last_chapter_title"] == "第3章 結局"


class TestAuthorBooks:
    def test_author_with_books(self, client, mock_fetch):
        """Author endpoint returns books by the given author."""
        import db_models
        from cache_manager import generate_public_id

        session = db_models.db_manager.get_session()
        try:
            b1 = db_models.Book(
                id="auth1_book1", public_id=generate_public_id(),
                name="Book A", author="TestAuthor", type="玄幻",
                view_count=100,
            )
            b2 = db_models.Book(
                id="auth1_book2", public_id=generate_public_id(),
                name="Book B", author="TestAuthor", type="言情",
                view_count=200,
            )
            session.add_all([b1, b2])
            session.commit()
        finally:
            session.close()

        resp = client.get(f"{BASE}/authors/TestAuthor/books")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # Should be ordered by view_count desc
        assert data[0]["bookname"] == "Book B"
        assert data[1]["bookname"] == "Book A"

    def test_author_no_books(self, client, mock_fetch):
        resp = client.get(f"{BASE}/authors/NonExistent/books")
        assert resp.status_code == 200
        assert resp.json() == []


class TestSimilarBooks:
    def test_similar_by_author_and_type(self, client, mock_fetch):
        """Similar books returns books by same author or type, excluding self."""
        import db_models
        from cache_manager import generate_public_id

        session = db_models.db_manager.get_session()
        try:
            current = db_models.Book(
                id="sim_current", public_id=generate_public_id(),
                name="Current Book", author="SimAuthor", type="玄幻",
                view_count=50,
            )
            same_author = db_models.Book(
                id="sim_author", public_id=generate_public_id(),
                name="Same Author Book", author="SimAuthor", type="言情",
                view_count=300,
            )
            same_type = db_models.Book(
                id="sim_type", public_id=generate_public_id(),
                name="Same Type Book", author="OtherAuthor", type="玄幻",
                view_count=200,
            )
            unrelated = db_models.Book(
                id="sim_unrelated", public_id=generate_public_id(),
                name="Unrelated", author="Someone", type="歷史",
                view_count=500,
            )
            session.add_all([current, same_author, same_type, unrelated])
            session.commit()
        finally:
            session.close()

        resp = client.get(f"{BASE}/books/sim_current/similar")
        assert resp.status_code == 200
        data = resp.json()
        ids = [b["book_id"] for b in data]
        assert "sim_author" in ids
        assert "sim_type" in ids
        assert "sim_current" not in ids
        assert "sim_unrelated" not in ids
        # Ordered by view_count desc
        assert data[0]["bookname"] == "Same Author Book"

    def test_similar_book_not_found(self, client, mock_fetch):
        resp = client.get(f"{BASE}/books/nonexistent999/similar")
        assert resp.status_code == 200
        assert resp.json() == []


class TestChaptersWithVolumes:
    def test_chapters_all_returns_volumes(self, client, mock_fetch):
        """When fetching all chapters, volumes should be included."""
        mock_fetch.register(
            "https://czbooks.net/n/testbook", CZBOOKS_BOOK_DETAIL_HTML
        )
        resp = client.get(f"{BASE}/books/testbook/chapters?all=true")
        assert resp.status_code == 200
        data = resp.json()
        # Response should be a dict with chapters and volumes
        assert isinstance(data, dict)
        assert "chapters" in data
        assert "volumes" in data
        assert len(data["chapters"]) == 3
        assert len(data["volumes"]) == 1
        assert data["volumes"][0]["name"] == "第一卷 起始"
        assert data["volumes"][0]["start_chapter"] == 1

    def test_chapters_paginated_returns_list(self, client, mock_fetch):
        """Paginated mode still returns a flat list for backward compat."""
        mock_fetch.register(
            "https://czbooks.net/n/testbook", CZBOOKS_BOOK_DETAIL_HTML
        )
        resp = client.get(f"{BASE}/books/testbook/chapters?page=1")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


class TestSearch:
    def test_search_books(self, client, mock_fetch):
        import db_models

        session = db_models.db_manager.get_session()
        try:
            book = db_models.Book(id="searchtest", name="搜尋測試小說", author="搜尋作者")
            session.add(book)
            session.commit()
        finally:
            session.close()

        resp = client.get(f"{BASE}/search?q=搜尋測試")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_results"] > 0


class TestByUrl:
    def test_chapters_by_url(self, client, mock_fetch):
        mock_fetch.register(
            "https://czbooks.net/n/testbook", CZBOOKS_BOOK_DETAIL_HTML
        )
        resp = client.get(
            f"{BASE}/by-url/chapters",
            params={"book_url": "https://czbooks.net/n/testbook"},
        )
        assert resp.status_code == 200
        chapters = resp.json()
        assert len(chapters) == 3

    def test_content_by_url(self, client, mock_fetch):
        mock_fetch.register(
            "https://czbooks.net/n/testbook/ch1", CZBOOKS_CHAPTER_DETAIL_HTML
        )
        resp = client.get(
            f"{BASE}/by-url/content",
            params={"chapter_url": "https://czbooks.net/n/testbook/ch1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "第1章 開始"
        assert "故事從這裡開始" in data["text"]

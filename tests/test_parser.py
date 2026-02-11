"""Unit tests for parser.py — pure function tests, no network calls."""
import pytest
from parser import (
    extract_text_by_id,
    extract_text_by_selector,
    extract_chapter_title,
    chinese_to_arabic,
    chapter_title_to_number,
    extract_book_id_from_url,
    find_categories_from_nav,
    parse_books,
    parse_book_info,
    fetch_chapters_from_liebiao,
    _normalize_czbooks_url,
)
from html_fixtures import (
    CZBOOKS_HOMEPAGE_HTML,
    CZBOOKS_CATEGORY_PAGE_HTML,
    CZBOOKS_BOOK_DETAIL_HTML,
    CZBOOKS_CHAPTER_DETAIL_HTML,
)


# ===== extract_text_by_id =====

class TestExtractTextById:
    def test_basic(self):
        html = '<div id="msg">Hello World</div>'
        assert extract_text_by_id(html, "msg") == "Hello World"

    def test_nested_html(self):
        html = '<div id="msg"><p>First</p><p>Second</p></div>'
        result = extract_text_by_id(html, "msg")
        assert "First" in result
        assert "Second" in result

    def test_missing_element(self):
        html = '<div id="other">text</div>'
        assert extract_text_by_id(html, "msg") == ""

    def test_html_entities(self):
        html = '<div id="msg">A &amp; B &lt; C</div>'
        result = extract_text_by_id(html, "msg")
        assert "A & B < C" in result


# ===== extract_text_by_selector =====

class TestExtractTextBySelector:
    def test_basic(self):
        html = '<div class="content"><p>Hello</p></div>'
        assert extract_text_by_selector(html, "div.content") == "Hello"

    def test_missing_selector(self):
        html = '<div class="other">text</div>'
        assert extract_text_by_selector(html, "div.content") == ""


# ===== extract_chapter_title =====

class TestExtractChapterTitle:
    def test_czbooks_div_name(self):
        title = extract_chapter_title(CZBOOKS_CHAPTER_DETAIL_HTML)
        assert title == "第1章 開始"

    def test_h1_strategy(self):
        html = "<html><body><h1>第五十章 決戰</h1></body></html>"
        assert extract_chapter_title(html) == "第五十章 決戰"

    def test_page_title_strategy(self):
        html = "<html><head><title>第三章 出發 - 小說名</title></head><body></body></html>"
        title = extract_chapter_title(html)
        assert title is not None
        assert "第三章" in title

    def test_no_match(self):
        html = "<html><body><p>No chapter here</p></body></html>"
        assert extract_chapter_title(html) is None


# ===== chinese_to_arabic =====

@pytest.mark.parametrize(
    "chinese,expected",
    [
        ("十", 10),
        ("三十", 30),
        ("十五", 15),
        ("六百八十", 680),
        ("一千二百三十四", 1234),
        ("一万", 10000),
        ("五", 5),
        ("", None),
    ],
)
def test_chinese_to_arabic(chinese, expected):
    assert chinese_to_arabic(chinese) == expected


# ===== chapter_title_to_number =====

class TestChapterTitleToNumber:
    def test_arabic(self):
        assert chapter_title_to_number("第123章 標題") == 123

    def test_chinese(self):
        assert chapter_title_to_number("第三十章 戰鬥") == 30

    def test_no_match(self):
        assert chapter_title_to_number("序章 開始") is None


# ===== extract_book_id_from_url =====

class TestExtractBookIdFromUrl:
    def test_czbooks(self):
        assert extract_book_id_from_url("https://czbooks.net/n/cr382b") == "cr382b"

    def test_with_chapter_path(self):
        assert extract_book_id_from_url("https://czbooks.net/n/cr382b/crdic") == "cr382b"

    def test_protocol_relative(self):
        assert extract_book_id_from_url("//czbooks.net/n/abc123") == "abc123"

    def test_legacy_numeric(self):
        assert extract_book_id_from_url("https://m.xsw.tw/12345/") == "12345"

    def test_no_match(self):
        assert extract_book_id_from_url("https://example.com/page") is None


# ===== find_categories_from_nav =====

class TestFindCategoriesFromNav:
    def test_czbooks_nav_links(self):
        cats = find_categories_from_nav(CZBOOKS_HOMEPAGE_HTML, "https://czbooks.net")
        assert len(cats) == 2
        ids = {c["id"] for c in cats}
        assert ids == {"xuanhuan", "yanqing"}
        for c in cats:
            assert "id" in c
            assert "name" in c
            assert "url" in c

    def test_deduplication(self):
        # Homepage HTML has xuanhuan listed twice
        cats = find_categories_from_nav(CZBOOKS_HOMEPAGE_HTML, "https://czbooks.net")
        xuanhuan_count = sum(1 for c in cats if c["id"] == "xuanhuan")
        assert xuanhuan_count == 1

    def test_empty_html(self):
        cats = find_categories_from_nav("<html><body></body></html>", "https://czbooks.net")
        assert cats == []


# ===== parse_books =====

class TestParseBooks:
    def test_czbooks_structure(self):
        books = parse_books(CZBOOKS_CATEGORY_PAGE_HTML, "https://czbooks.net")
        assert len(books) == 2
        assert books[0]["bookname"] == "第一本書"
        assert books[0]["author"] == "作者一"
        assert books[1]["bookname"] == "第二本書"
        assert books[1]["author"] == "作者二"

    def test_url_normalization(self):
        books = parse_books(CZBOOKS_CATEGORY_PAGE_HTML, "https://czbooks.net")
        for book in books:
            assert book["bookurl"].startswith("https://")

    def test_empty_html(self):
        books = parse_books("<html><body></body></html>", "https://czbooks.net")
        assert books == []


# ===== parse_book_info =====

class TestParseBookInfo:
    def test_czbooks_detail(self):
        info = parse_book_info(CZBOOKS_BOOK_DETAIL_HTML, "https://czbooks.net")
        assert info["name"] == "測試小說"  # 《》 stripped
        assert info["author"] == "測試作者"
        assert info["type"] == "玄幻"
        assert info["status"] == "連載中"
        assert info["update"] == "2026-02-01"
        assert info["last_chapter_number"] == 3

    def test_last_chapter_info(self):
        info = parse_book_info(CZBOOKS_BOOK_DETAIL_HTML, "https://czbooks.net")
        assert info["last_chapter_title"] == "第3章 結局"
        assert "czbooks.net" in info["last_chapter_url"]

    def test_empty_html(self):
        info = parse_book_info("<html><body></body></html>", "https://czbooks.net")
        assert info == {}


# ===== fetch_chapters_from_liebiao =====

class TestFetchChaptersFromLiebiao:
    BASE = "https://czbooks.net"
    PAGE_URL = "https://czbooks.net/n/testbook"

    def test_czbooks_chapter_list(self):
        chapters = fetch_chapters_from_liebiao(
            CZBOOKS_BOOK_DETAIL_HTML, self.PAGE_URL, self.BASE
        )
        assert len(chapters) == 3
        assert chapters[0]["number"] == 1
        assert chapters[1]["number"] == 2
        assert chapters[2]["number"] == 3
        assert "第1章 開始" in chapters[0]["title"]

    def test_skip_volume_marker(self):
        chapters = fetch_chapters_from_liebiao(
            CZBOOKS_BOOK_DETAIL_HTML, self.PAGE_URL, self.BASE
        )
        # Volume marker "第一卷 起始" should not appear
        titles = [ch["title"] for ch in chapters]
        assert not any("第一卷" in t for t in titles)

    def test_sequential_indexing(self):
        chapters = fetch_chapters_from_liebiao(
            CZBOOKS_BOOK_DETAIL_HTML, self.PAGE_URL, self.BASE
        )
        numbers = [ch["number"] for ch in chapters]
        assert numbers == [1, 2, 3]

    def test_start_index(self):
        chapters = fetch_chapters_from_liebiao(
            CZBOOKS_BOOK_DETAIL_HTML, self.PAGE_URL, self.BASE, start_index=51
        )
        numbers = [ch["number"] for ch in chapters]
        assert numbers == [51, 52, 53]

    def test_url_normalization(self):
        chapters = fetch_chapters_from_liebiao(
            CZBOOKS_BOOK_DETAIL_HTML, self.PAGE_URL, self.BASE
        )
        for ch in chapters:
            assert ch["url"].startswith("https://czbooks.net/")

    def test_legacy_fallback(self):
        legacy_html = """\
        <html><body>
        <div class="liebiao">
          <ul>
            <li><a href="/123/1.html">第1章</a></li>
            <li><a href="/123/2.html">第2章</a></li>
          </ul>
        </div>
        </body></html>
        """
        chapters = fetch_chapters_from_liebiao(
            legacy_html, "https://czbooks.net/123/", self.BASE
        )
        assert len(chapters) == 2
        assert chapters[0]["number"] == 1
        assert chapters[1]["number"] == 2

    def test_empty_html(self):
        chapters = fetch_chapters_from_liebiao(
            "<html><body></body></html>", self.PAGE_URL, self.BASE
        )
        assert chapters == []


# ===== _normalize_czbooks_url =====

class TestNormalizeCzbooksUrl:
    def test_protocol_relative(self):
        result = _normalize_czbooks_url("//czbooks.net/n/abc", "https://czbooks.net")
        assert result == "https://czbooks.net/n/abc"

    def test_relative_path(self):
        result = _normalize_czbooks_url("/n/abc", "https://czbooks.net")
        assert result == "https://czbooks.net/n/abc"

    def test_absolute_url(self):
        result = _normalize_czbooks_url(
            "https://czbooks.net/n/abc", "https://czbooks.net"
        )
        assert result == "https://czbooks.net/n/abc"

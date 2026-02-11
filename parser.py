# parser.py
"""
HTML parsing functions for czbooks.net.
All parsing logic centralized here for easier testing and maintenance.
"""
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup
import html as html_unescape
import re
from urllib.parse import urljoin


def extract_text_by_id(html_content: str, element_id: str) -> str:
    """
    Extract and normalize text from an element by id.
    Preserves logical breaks, normalizes whitespace.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    target = soup.find(id=element_id)
    if not target:
        return ""
    text_content = html_unescape.unescape(target.get_text(separator="\n"))
    normalized = re.sub(r"\s+", " ", text_content).strip()
    return normalized


def extract_text_by_selector(html_content: str, selector: str) -> str:
    """
    Extract and normalize text from an element matched by CSS selector.
    Preserves logical breaks, normalizes whitespace.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    target = soup.select_one(selector)
    if not target:
        return ""
    text_content = html_unescape.unescape(target.get_text(separator="\n"))
    normalized = re.sub(r"\s+", " ", text_content).strip()
    return normalized


def extract_chapter_title(html_content: str) -> Optional[str]:
    """
    Extract chapter title from a chapter page.
    Tries multiple strategies to find the title.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # Strategy 1 (czbooks): Look for div.name inside .chapter-detail
    chapter_detail = soup.select_one(".chapter-detail")
    if chapter_detail:
        name_div = chapter_detail.select_one("div.name")
        if name_div:
            title = name_div.get_text(strip=True)
            if title:
                return title

    # Strategy 2: Look for h1 with chapter pattern
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
        if re.search(r"第.+章", title):
            return title

    # Strategy 3: Look for div/h2 with class containing "title" or "chapter"
    for tag in soup.find_all(["h1", "h2", "h3", "div"], class_=re.compile(r"(title|chapter|tit)", re.I)):
        title = tag.get_text(strip=True)
        if re.search(r"第.+章", title):
            return title

    # Strategy 4: Look in page title
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)
        # Extract just the chapter part if it exists
        match = re.search(r"(第.+章[^_\-—]*)", title)
        if match:
            return match.group(1).strip()

    return None


def parse_chapters(html_content: str, base_url: str = "") -> Dict[int, Dict[str, str]]:
    """
    Parse <ul class="chapter"> into {chapter_number: {'url': full_url, 'title': title}}
    Supports both Arabic and Chinese numerals in chapter titles.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    chapters: Dict[int, Dict[str, str]] = {}
    ul = soup.find("ul", class_="chapter")
    if not ul:
        return chapters

    for a_tag in ul.find_all("a", href=True):
        raw_text = html_unescape.unescape(a_tag.get_text(strip=True))
        href = a_tag["href"]
        chapter_num = chapter_title_to_number(raw_text)
        if chapter_num:
            title = raw_text
            full_url = urljoin(base_url or "", href)
            chapters[chapter_num] = {"url": full_url, "title": title}
    return chapters


def get_page_count(html_content: str) -> int:
    """
    Extract total pages from <div class="page"> e.g., (第1/70頁)
    """
    soup = BeautifulSoup(html_content, "html.parser")
    page_div = soup.find("div", class_="page")
    if not page_div:
        return 0
    text = page_div.get_text(strip=True)
    m = re.search(r"第\d+/(\d+)頁", text)
    return int(m.group(1)) if m else 0


def parse_book_info(html_content: str, base_url: str = "") -> Dict[str, Any]:
    """
    Parse book detail page from czbooks.net.
    Looks for div.novel-detail with .info and .description sections.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # czbooks.net structure: div.novel-detail
    detail = soup.select_one("div.novel-detail")
    if not detail:
        return {}

    # Book name from .info .title
    name = ""
    title_el = detail.select_one(".info .title")
    if title_el:
        name = title_el.get_text(strip=True)
        # Strip surrounding 《》 if present
        name = re.sub(r'^[《\u300a]|[》\u300b]$', '', name).strip()

    # Author from .info .author a
    author = ""
    author_el = detail.select_one(".info .author a")
    if author_el:
        author = author_el.get_text(strip=True)

    # Status and stats from .state table
    status = ""
    update = ""
    state_table = detail.select_one(".state table")
    if state_table:
        rows = state_table.select("tr")
        for row in rows:
            cells = row.select("td")
            for i in range(0, len(cells) - 1, 2):
                label = cells[i].get_text(strip=True)
                value = cells[i + 1].get_text(strip=True) if i + 1 < len(cells) else ""
                if "狀態" in label or "状态" in label:
                    status = value
                elif "更新" in label:
                    update = value

    # Category from a#novel-category
    book_type = ""
    cat_el = detail.select_one("a#novel-category")
    if cat_el:
        book_type = cat_el.get_text(strip=True)

    # Description
    desc = ""
    desc_el = detail.select_one(".description")
    if desc_el:
        desc = desc_el.get_text(strip=True)

    # Count chapters from ul.chapter-list to get last chapter info
    last_chapter_title = ""
    last_chapter_url = ""
    last_chapter_number: Optional[int] = None

    chapter_list = soup.select("ul.chapter-list li a")
    if chapter_list:
        # Filter out volume markers (li.volume items don't have <a> children usually)
        last_a = chapter_list[-1]
        last_chapter_title = last_a.get_text(strip=True)
        href = last_a.get("href", "")
        last_chapter_url = _normalize_czbooks_url(href, base_url)
        last_chapter_number = len(chapter_list)

    return {
        "name": name,
        "author": author,
        "type": book_type,
        "status": status,
        "update": update,
        "description": desc,
        "last_chapter_title": last_chapter_title,
        "last_chapter_url": last_chapter_url,
        "last_chapter_number": last_chapter_number,
    }


def _normalize_czbooks_url(href: str, base_url: str) -> str:
    """
    Normalize czbooks.net URLs which may be protocol-relative (//czbooks.net/...).
    """
    if href.startswith("//"):
        return "https:" + href
    return urljoin(base_url or "", href)


def parse_books(html: str, base_url: str = "") -> List[Dict[str, str]]:
    """
    Parse book list from czbooks.net category page.
    Each book is in li.novel-item-wrapper > div.novel-item.
    returns [{bookname, author, lastchapter, intro, bookurl, date}, ...]
    """
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict[str, str]] = []

    for wrapper in soup.select("li.novel-item-wrapper"):
        item = wrapper.select_one("div.novel-item")
        if not item:
            continue

        # Title and book URL from .novel-item-cover-wrapper a
        bookname = ""
        bookurl = ""
        cover_link = item.select_one(".novel-item-cover-wrapper a[href]")
        if cover_link:
            href = cover_link.get("href", "")
            bookurl = _normalize_czbooks_url(href, base_url)
            title_el = cover_link.select_one(".novel-item-title")
            if title_el:
                bookname = title_el.get_text(strip=True)

        # Author
        author = ""
        author_el = item.select_one(".novel-item-author a")
        if author_el:
            author = author_el.get_text(strip=True)

        # Last chapter
        lastchapter = ""
        lasturl = ""
        chapter_el = item.select_one(".novel-item-newest-chapter a")
        if chapter_el:
            lastchapter = chapter_el.get_text(strip=True)
            href = chapter_el.get("href", "")
            lasturl = _normalize_czbooks_url(href, base_url)

        # No intro field on czbooks list pages
        intro = ""

        out.append(
            {
                "bookname": bookname,
                "author": author,
                "lastchapter": lastchapter,
                "lasturl": lasturl,
                "intro": intro,
                "bookurl": bookurl,
            }
        )
    return out


def chinese_to_arabic(chinese_num: str) -> Optional[int]:
    """
    Convert Chinese numerals to Arabic numerals.
    Examples:
        '六百八十' -> 680
        '一千二百三十四' -> 1234
        '三十' -> 30
        '五' -> 5
        '十' -> 10
        '一万' -> 10000
    """
    # Chinese digit mapping
    chinese_digits = {
        '零': 0, '〇': 0,
        '一': 1, '壹': 1,
        '二': 2, '贰': 2, '貳': 2, '两': 2, '兩': 2,
        '三': 3, '叁': 3, '參': 3,
        '四': 4, '肆': 4,
        '五': 5, '伍': 5,
        '六': 6, '陆': 6, '陸': 6,
        '七': 7, '柒': 7,
        '八': 8, '捌': 8,
        '九': 9, '玖': 9,
    }

    # Chinese unit mapping
    chinese_units = {
        '十': 10, '拾': 10,
        '百': 100, '佰': 100,
        '千': 1000, '仟': 1000,
        '万': 10000, '萬': 10000,
    }

    result = 0
    section = 0  # Current section value (before hitting 万)
    temp_num = 0  # Temporary number before unit

    i = 0
    while i < len(chinese_num):
        char = chinese_num[i]

        if char in chinese_digits:
            temp_num = chinese_digits[char]
            i += 1
        elif char in chinese_units:
            unit_value = chinese_units[char]

            # Special case: 十 at the beginning (e.g., 十五 = 15, 十 = 10)
            if unit_value == 10 and temp_num == 0 and section == 0 and result == 0:
                temp_num = 1

            if unit_value == 10000:  # 万
                # Complete the current section and multiply by 万
                section = (section + temp_num) if temp_num > 0 else section
                result += section * unit_value
                section = 0
                temp_num = 0
            else:
                # Regular units (十, 百, 千)
                section += temp_num * unit_value
                temp_num = 0
            i += 1
        else:
            # Skip unknown characters
            i += 1

    # Add remaining values
    result += section + temp_num
    return result if result > 0 else None


def chapter_title_to_number(title: str) -> Optional[int]:
    """
    Extract numeric chapter index from chapter titles.
    Supports both Arabic and Chinese numerals:
        '第1199章 XXX' -> 1199
        '第六百八十章 XXX' -> 680
        '第一千二百三十四章 XXX' -> 1234
    """
    # Try Arabic numerals first
    m = re.search(r"第\s*(\d+)\s*章", title)
    if m:
        return int(m.group(1))

    # Try Chinese numerals
    m = re.search(r"第\s*([零〇一二三四五六七八九十百千万壹贰貳叁參肆伍陆陸柒捌玖拾佰仟萬兩两]+)\s*章", title)
    if m:
        chinese_num = m.group(1)
        return chinese_to_arabic(chinese_num)

    return None


def fetch_chapters_from_liebiao(
    html_content: str, page_url: str, canonical_base: str, start_index: int = 1
) -> List[Dict[str, Any]]:
    """
    Parse chapter list from czbooks.net book page.
    czbooks.net has all chapters in ul.chapter-list on the book detail page.
    Falls back to old selectors (div.liebiao, ul.chapter) for cached pages.

    - `page_url` should be the book page URL (so relative hrefs join correctly)
    - Rewrites final URLs to the canonical site host
    - Uses sequential indices starting from `start_index`
    - Skips volume markers (li.volume)

    Returns: [{ 'url': absolute_url, 'title': str, 'number': int }, ...]
    """
    from urllib.parse import urlparse, urlunparse

    soup = BeautifulSoup(html_content, "html.parser")

    # Strategy 1 (czbooks.net): ul.chapter-list
    container = soup.select_one("ul.chapter-list")
    if container:
        out: List[Dict[str, Any]] = []
        chapter_index = start_index
        for li in container.find_all("li", recursive=False):
            # Skip volume markers (li.volume)
            if "volume" in li.get("class", []):
                continue
            a_tag = li.find("a", href=True)
            if not a_tag:
                continue
            href = a_tag["href"]
            title = a_tag.get_text(strip=True)
            # Normalize URL (czbooks uses protocol-relative //czbooks.net/...)
            absolute = _normalize_czbooks_url(href, page_url)
            # Rewrite host to canonical
            target = urlparse(absolute)
            base = urlparse(canonical_base)
            absolute = urlunparse(
                (base.scheme, base.netloc, target.path, target.params, target.query, target.fragment)
            )
            out.append(
                {
                    "url": absolute,
                    "title": title,
                    "number": chapter_index,
                }
            )
            chapter_index += 1
        return out

    # Strategy 2 (legacy): div.liebiao or ul.chapter
    container = soup.find("div", class_="liebiao")
    if not container:
        container = soup.find("ul", class_="chapter")
    if not container:
        return []

    out = []
    selector = "ul li a[href]" if container.name == "div" else "li a[href]"
    chapter_index = start_index
    for a_tag in container.select(selector):
        href = a_tag["href"]
        title = a_tag.get_text(strip=True)
        absolute = urljoin(page_url, href)
        target = urlparse(absolute)
        base = urlparse(canonical_base)
        absolute = urlunparse(
            (base.scheme, base.netloc, target.path, target.params, target.query, target.fragment)
        )
        out.append(
            {
                "url": absolute,
                "title": title,
                "number": chapter_index,
            }
        )
        chapter_index += 1
    return out


def find_categories_from_nav(home_html: str, base_url: str) -> List[Dict[str, str]]:
    """
    Parse category links from czbooks.net navigation.
    Looks for anchors with href matching /c/{slug} pattern.
    Falls back to old fenlei pattern for cached pages.
    """
    soup = BeautifulSoup(home_html, "html.parser")
    cats: List[Dict[str, str]] = []

    # Strategy 1 (czbooks.net): Look for /c/{slug} links in nav menu
    nav_links = soup.select("ul.nav.menu li a[href]")
    if not nav_links:
        # Broader search: any anchor with /c/ pattern
        nav_links = soup.find_all("a", href=True)

    for a in nav_links:
        href = a.get("href", "")
        # Match czbooks category pattern: //czbooks.net/c/{slug} or /c/{slug}
        m = re.search(r"(?:https?:)?//czbooks\.net/c/(\w+)", href)
        if not m:
            m = re.search(r"^/c/(\w+)$", href)
        if m:
            cat_slug = m.group(1)
            full_url = _normalize_czbooks_url(href, base_url)
            cats.append(
                {
                    "id": cat_slug,
                    "name": a.get_text(strip=True),
                    "url": full_url,
                }
            )

    # Strategy 2 (legacy): fenlei pattern
    if not cats:
        anchors = soup.find_all("a", href=True)
        for a in anchors:
            href = a["href"]
            if re.search(r"fenlei(\d+)_1\.html", href):
                m = re.search(r"fenlei(\d+)_1\.html", href)
                cat_id = m.group(1) if m else ""
                cats.append(
                    {
                        "id": cat_id,
                        "name": a.get_text(),
                        "url": urljoin(base_url + "/", href),
                    }
                )

    # Deduplicate by id
    seen = set()
    uniq = []
    for c in cats:
        if c["id"] not in seen:
            uniq.append(c)
            seen.add(c["id"])
    return uniq


def extract_book_id_from_url(bookurl: str) -> Optional[str]:
    """
    Extract book ID from URL pattern.
    czbooks.net: //czbooks.net/n/{book_id} or https://czbooks.net/n/{book_id}
    Legacy: https://m.xsw.tw/{book_id}/
    """
    # czbooks.net pattern: /n/{book_id}
    m = re.search(r"/n/([^/?#]+)", bookurl)
    if m:
        return m.group(1)
    # Legacy pattern: /{numeric_id}/
    m = re.search(r"https?://[^/]+/(\d+)/", bookurl)
    return m.group(1) if m else None

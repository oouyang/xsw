# parser.py
"""
HTML parsing functions extracted from main.py for better modularity.
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


def extract_chapter_title(html_content: str) -> Optional[str]:
    """
    Extract chapter title from a chapter page.
    Tries multiple strategies to find the title.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # Strategy 1: Look for h1 with chapter pattern
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
        if re.search(r"第.+章", title):
            return title

    # Strategy 2: Look for div/h2 with class containing "title" or "chapter"
    for tag in soup.find_all(["h1", "h2", "h3", "div"], class_=re.compile(r"(title|chapter|tit)", re.I)):
        title = tag.get_text(strip=True)
        if re.search(r"第.+章", title):
            return title

    # Strategy 3: Look in page title
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
    Parse <div class="block_txt2"> for book details.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    block = soup.find("div", class_="block_txt2")
    if not block:
        return {}

    name = block.find("h2").get_text(strip=True) if block.find("h2") else ""

    status_tag = block.find("p", string=lambda t: t and "狀態" in t)
    status = status_tag.get_text(strip=True).replace("狀態：", "") if status_tag else ""

    update_tag = block.find("p", string=lambda t: t and "更新" in t)
    update = update_tag.get_text(strip=True).replace("更新：", "") if update_tag else ""

    author = ""
    book_type = ""
    last_chapter_title = ""
    last_chapter_url = ""
    last_chapter_number: Optional[int] = None

    for p in block.find_all("p"):
        text = p.get_text(strip=True)
        if text.startswith("作者"):
            a_tag = p.find("a")
            author = a_tag.get_text(strip=True) if a_tag else ""
        elif text.startswith("分類"):
            a_tag = p.find("a")
            book_type = a_tag.get_text(strip=True) if a_tag else ""
        elif text.startswith("最新"):
            a_tag = p.find("a")
            if a_tag:
                last_chapter_title = a_tag.get_text(strip=True)
                href = a_tag.get("href", "")
                last_chapter_url = urljoin(base_url or "", href)
                last_chapter_number = chapter_title_to_number(last_chapter_title)

    return {
        "name": name,
        "author": author,
        "type": book_type,
        "status": status,
        "update": update,
        "last_chapter_title": last_chapter_title,
        "last_chapter_url": last_chapter_url,
        "last_chapter_number": last_chapter_number,
    }


def parse_books(html: str, base_url: str = "") -> List[Dict[str, str]]:
    """
    Parse book list boxes:
    returns [{bookname, author, lastchapter, intro, bookurl}, ...]
    """
    soup = BeautifulSoup(html, "lxml")
    out: List[Dict[str, str]] = []
    for box in soup.select("div.bookbox"):
        name_tag = box.select_one("div.bookinfo h4.bookname i.iTit a")
        bookname = (name_tag.get_text(strip=True) if name_tag else "").strip()
        href = name_tag.get("href", "") if name_tag else ""
        bookurl = urljoin(base_url or "", href)

        author_tag = box.select_one("div.bookinfo div.author")
        author_raw = author_tag.get_text(" ", strip=True) if author_tag else ""
        author = author_raw.replace("作者：", "").replace("作者:", "").strip()

        chapter_tag = box.select_one("div.bookinfo div.update a")
        lastchapter = chapter_tag.get_text(strip=True).strip() if chapter_tag else ""
        href = chapter_tag.get("href", "") if chapter_tag else ""
        lasturl = urljoin(base_url or "", href) if href else ""

        intro_tag = box.select_one("div.bookinfo div.intro_line")
        intro_text = intro_tag.get_text(" ", strip=True) if intro_tag else ""
        intro = intro_text.replace("簡介：", "").replace("简介：", "").strip()

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
    Parse chapter list from either <div class="liebiao"> or <ul class="chapter">.
    - `page_url` should be the book HOME URL (so relative hrefs join correctly)
    - Rewrites final URLs to the canonical site host to avoid mixing m/www
    - Uses sequential indices starting from `start_index` instead of parsing chapter numbers from titles
    - This prevents gaps when chapter titles don't contain numbers

    Returns: [{ 'url': absolute_url, 'title': str, 'number': int }, ...]
    """
    from urllib.parse import urlparse, urlunparse

    soup = BeautifulSoup(html_content, "html.parser")

    # Try to find chapter container (mobile uses ul.chapter, desktop uses div.liebiao)
    container = soup.find("div", class_="liebiao")
    if not container:
        container = soup.find("ul", class_="chapter")
    if not container:
        return []

    out: List[Dict[str, Any]] = []
    # For div.liebiao, chapters are in ul li a; for ul.chapter, chapters are direct li a
    selector = "ul li a[href]" if container.name == "div" else "li a[href]"
    chapter_index = start_index
    for a_tag in container.select(selector):
        href = a_tag["href"]
        title = a_tag.get_text(strip=True)
        # join using the page URL (book home) to keep folder context intact
        absolute = urljoin(page_url, href)
        # rewrite host to canonical (prevents mixing m/www)
        target = urlparse(absolute)
        base = urlparse(canonical_base)
        absolute = urlunparse(
            (base.scheme, base.netloc, target.path, target.params, target.query, target.fragment)
        )
        out.append(
            {
                "url": absolute,
                "title": title,
                "number": chapter_index,  # Use sequential index instead of parsed number
            }
        )
        chapter_index += 1
    return out


def find_categories_from_nav(home_html: str, base_url: str) -> List[Dict[str, str]]:
    """
    Best-effort approach: find anchors linking to 'fenleiX_1.html' in nav/header.
    """
    soup = BeautifulSoup(home_html, "html.parser")
    cats: List[Dict[str, str]] = []
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
    """Extract book ID from URL pattern."""
    m = re.search(r"https?://[^/]+/(\d+)/", bookurl)
    return m.group(1) if m else None

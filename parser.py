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


def parse_chapters(html_content: str, base_url: str = "") -> Dict[int, Dict[str, str]]:
    """
    Parse <ul class="chapter"> into {chapter_number: {'url': full_url, 'title': title}}
    """
    soup = BeautifulSoup(html_content, "html.parser")
    chapters: Dict[int, Dict[str, str]] = {}
    ul = soup.find("ul", class_="chapter")
    if not ul:
        return chapters

    for a_tag in ul.find_all("a", href=True):
        raw_text = html_unescape.unescape(a_tag.get_text(strip=True))
        href = a_tag["href"]
        match = re.search(r"第(\d+)章", raw_text)
        if match:
            chapter_num = int(match.group(1))
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
                match = re.search(r"第(\d+)章", last_chapter_title)
                if match:
                    last_chapter_number = int(match.group(1))

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

        intro_tag = box.select_one("div.bookinfo div.intro_line")
        intro_text = intro_tag.get_text(" ", strip=True) if intro_tag else ""
        intro = intro_text.replace("簡介：", "").replace("简介：", "").strip()

        out.append(
            {
                "bookname": bookname,
                "author": author,
                "lastchapter": lastchapter,
                "intro": intro,
                "bookurl": bookurl,
            }
        )
    return out


def chapter_title_to_number(title: str) -> Optional[int]:
    """
    Extract numeric chapter index from '第1199章 XXX'.
    """
    m = re.search(r"第\s*(\d+)\s*章", title)
    return int(m.group(1)) if m else None


def fetch_chapters_from_liebiao(
    html_content: str, page_url: str, canonical_base: str
) -> List[Dict[str, Any]]:
    """
    Parse <div class="liebiao"> chapter list.
    - `page_url` should be the book HOME URL (so relative hrefs join correctly)
    - Rewrites final URLs to the canonical site host to avoid mixing m/www

    Returns: [{ 'url': absolute_url, 'title': str, 'number': int|None }, ...]
    """
    from urllib.parse import urlparse, urlunparse

    soup = BeautifulSoup(html_content, "html.parser")
    container = soup.find("div", class_="liebiao")
    if not container:
        return []

    out: List[Dict[str, Any]] = []
    for a_tag in container.select("ul li a[href]"):
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
                "number": chapter_title_to_number(title),
            }
        )
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

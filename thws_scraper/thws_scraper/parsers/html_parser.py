from datetime import datetime
from typing import Optional
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from readability import Document
from scrapy.http import Response

from ..items import RawPageItem
from ..utils.text import clean_text


def parse_html(response: Response) -> Optional[RawPageItem]:
    """
    Extract the main content of an HTML page using Readability+BeautifulSoup.
    Returns a RawPageItem or None if the page is empty or a 404/no-content.
    """
    doc = Document(response.text)
    summary_html = doc.summary()
    soup = BeautifulSoup(summary_html, "lxml")
    text = clean_text(soup.get_text())

    # drop empty pages or obvious 404 pages
    if not text or "404" in text.lower() or "not found" in text.lower():
        return None

    # Title: prefer <h1>, fall back to <title>
    h1 = soup.select_one("h1")
    title = (
        h1.get_text(strip=True) if h1 else response.css("title::text").get("").strip()
    )

    # Try a few common date selectors
    date_updated = None
    for sel in (
        'meta[property="article:published_time"]::attr(content)',
        'meta[name="date"]::attr(content)',
        "time::text",
        ".date::text",
    ):
        d = response.css(sel).get()
        if d:
            date_updated = d.strip()
            break

    # Pull lang= from URL query, e.g. "?lang=de"
    qs = parse_qs(urlparse(response.url).query)
    lang = qs.get("lang", [None])[0] or "unknown"

    return RawPageItem(
        url=response.url,
        type="html",
        title=title,
        text=text,
        date_scraped=datetime.utcnow().isoformat(),
        date_updated=date_updated,
        status=response.status,
        lang=lang,
    )

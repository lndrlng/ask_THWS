import logging
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Comment
from scrapy.http import Response

from ..items import RawPageItem
from ..utils.date import date_extractor
from ..utils.lang import extract_lang_from_url

module_logger = logging.getLogger(__name__)


def _clean_html_fragment_for_storage(html_string: str) -> str:
    """
    Basic cleaning of an HTML fragment string.
    Removes script, style, comments, and common non-content boilerplate tags.
    """
    if not html_string:
        return ""

    soup = BeautifulSoup(html_string, "lxml")

    tags_to_decompose = [
        "script",
        "style",
        "noscript",
        "iframe",
        "header",
        "footer",
        "nav",
        "aside",
        "form",
    ]
    for tag_name in tags_to_decompose:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    return str(soup)


def parse_html(
    response: Response, soft_error_strings: List[str]
) -> Optional[Tuple[List[RawPageItem], List[str]]]:
    """
    1) Pick the main content container/subtree (heuristic-based).
    2) Extract its HTML structure.
    3) Clean the HTML fragment & wrap in a RawPageItem.
    4) Extract embedded .pdf/.ics links from the whole page.

    Args:
        response: The Scrapy HTTP response.
        soft_error_strings: A list of lowercase strings that indicate a soft error.
    """
    soup = BeautifulSoup(response.text, "lxml")

    container_candidate = soup.find("main") or soup.find("article")
    if not container_candidate:
        if soup.body:
            body_children = soup.body.find_all(recursive=False)
            if body_children:
                container_candidate = max(
                    body_children,
                    key=lambda el: len(el.get_text(strip=True, separator=" ")),
                    default=None,
                )
                if not container_candidate:
                    container_candidate = soup.body
            else:
                container_candidate = soup.body
        else:
            container_candidate = soup

    if not container_candidate:
        module_logger.warning(f"Could not identify any main content container for {response.url}")
        return None

    raw_main_html = str(container_candidate)
    cleaned_main_html = _clean_html_fragment_for_storage(raw_main_html)
    temp_cleaned_soup = BeautifulSoup(cleaned_main_html, "lxml")
    plain_text_for_check = temp_cleaned_soup.get_text(separator="\n", strip=True).lower()

    if not plain_text_for_check or any(msg in plain_text_for_check for msg in soft_error_strings):
        module_logger.info(
            f"Skipping page {response.url} due to soft error or empty content based on settings."
        )
        return None

    page_title_tag = soup.select_one("h1")
    page_title = (
        page_title_tag.get_text(strip=True)
        if page_title_tag
        else response.css("title::text").get("").strip()
    )
    if not page_title:
        page_title = "Untitled Page"

    item = RawPageItem(
        url=response.url,
        type="html",
        title=page_title,
        text=cleaned_main_html,
        date_scraped=datetime.utcnow().isoformat(),
        date_updated=date_extractor(response.text),
        status=response.status,
        lang=extract_lang_from_url(response.url),
    )

    items: List[RawPageItem] = [item]

    embedded_links: List[str] = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if href and href.lower().endswith((".pdf", ".ics")):
            abs_url = urljoin(response.url, href)
            embedded_links.append(abs_url)

    if not items:
        return None

    return items, embedded_links

import logging
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Comment
from lxml.html.clean import Cleaner
from readability import Document as ReadabilityDocument
from scrapy.http import Response

from ..items import RawPageItem
from ..utils.date import date_extractor
from ..utils.lang import detect_lang_from_content, extract_lang_from_url

module_logger = logging.getLogger(__name__)


def _clean_html_fragment_for_storage(html_string: str) -> str:
    """
    Cleans an HTML fragment string using lxml.html.clean.Cleaner
    and then removes all class and id attributes.
    Removes script, style, comments, and common non-content boilerplate tags.
    """
    if not html_string:
        return ""

    soup_for_comment_removal = BeautifulSoup(html_string, "lxml")
    for comment in soup_for_comment_removal.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    partially_cleaned_html = str(soup_for_comment_removal)

    cleaner = Cleaner(
        scripts=True,
        javascript=True,
        comments=True,
        style=True,
        inline_style=True,
        links=False,
        meta=False,
        page_structure=False,
        processing_instructions=True,
        embedded=True,
        frames=True,
        forms=False,
        annoying_tags=True,
        remove_tags=[
            "noscript",
            "header",
            "footer",
            "nav",
            "dialog",
            "menu",
        ],
        kill_tags=None,
        remove_unknown_tags=False,
        safe_attrs_only=False,
    )

    try:
        cleaned_html_lxml = cleaner.clean_html(partially_cleaned_html)
    except Exception as e:
        module_logger.warning(
            f"lxml.html.clean.Cleaner failed: {e}. Falling back to basic BS4 comment removal.",
            extra={
                "error_details": str(e),
                "event_type": "html_cleaning_error",
            },
        )
        cleaned_html_lxml = partially_cleaned_html

    final_soup = BeautifulSoup(cleaned_html_lxml, "lxml")
    for tag in final_soup.find_all(True):
        for attr_to_remove in ["class", "id", "style"]:
            if attr_to_remove in tag.attrs:
                del tag.attrs[attr_to_remove]
        on_event_attrs = [attr for attr in tag.attrs if attr.lower().startswith("on")]
        for attr in on_event_attrs:
            del tag.attrs[attr]

    return str(final_soup)


def extract_metadata(soup_full_page: BeautifulSoup) -> dict:
    """Extracts common metadata from the full page soup."""
    metadata = {
        "meta_description": None,
        "meta_keywords": None,
        "og_title": None,
        "og_description": None,
        "og_type": None,
        "og_url": None,
        "article_published_time": None,
        "article_modified_time": None,
    }

    def get_meta_content(attrs_dict):
        tag = soup_full_page.find("meta", attrs=attrs_dict)
        return tag["content"].strip() if tag and tag.get("content") else None

    metadata["meta_description"] = get_meta_content({"name": "description"})
    metadata["meta_keywords"] = get_meta_content({"name": "keywords"})
    metadata["og_title"] = get_meta_content({"property": "og:title"})
    metadata["og_description"] = get_meta_content({"property": "og:description"})
    metadata["og_type"] = get_meta_content({"property": "og:type"})
    metadata["og_url"] = get_meta_content({"property": "og:url"})
    metadata["article_published_time"] = get_meta_content({"property": "article:published_time"})
    metadata["article_modified_time"] = get_meta_content({"property": "article:modified_time"})
    return metadata


def parse_html(response: Response, soft_error_strings: List[str], tz: ZoneInfo) -> Optional[Tuple[List[RawPageItem], List[str]]]:
    """
    1) Use Readability to extract main content and title.
    2) Clean the extracted HTML fragment.
    3) Extract embedded .pdf/.ics links from the whole page.
    4) Extract common metadata from the whole page.
    5) Detect language from URL, then from content as fallback.
    6) Wrap in a RawPageItem.
    """
    try:
        readability_doc = ReadabilityDocument(response.text)
        raw_main_html_from_readability = readability_doc.summary()
        page_title_from_readability = readability_doc.title()
    except Exception as e:
        module_logger.warning(
            "Readability processing failed, attempting fallback to full body",
            extra={
                "event_type": "readability_error",
                "url": response.url,
                "error": str(e),
            },
        )
        soup_full_page_fallback = BeautifulSoup(response.text, "lxml")
        raw_main_html_from_readability = str(soup_full_page_fallback.body) if soup_full_page_fallback.body else response.text
        page_title_from_readability = soup_full_page_fallback.title.string if soup_full_page_fallback.title else ""

    if not raw_main_html_from_readability:
        module_logger.info(
            "Readability yielded no main content, proceeding to full text check",
            extra={"url": response.url, "event_type": "readability_empty_summary"},
        )
        temp_full_soup = BeautifulSoup(response.text, "lxml")
        plain_text_for_check_full = temp_full_soup.get_text(separator="\n", strip=True).lower()

        if not plain_text_for_check_full or any(msg in plain_text_for_check_full for msg in soft_error_strings):
            reason_skip = "empty_full_text_and_readability_empty"
            details = {"checked_full_text_length": len(plain_text_for_check_full)}
            soft_error_matches = [s for s in soft_error_strings if s in plain_text_for_check_full]
            if soft_error_matches:
                reason_skip = "soft_error_in_full_text_and_readability_empty"
                details["soft_errors_matched"] = soft_error_matches

            module_logger.info(
                "Skipped HTML: Readability empty & full text check failed",
                extra={
                    "event_type": "page_skipped_html",
                    "url": response.url,
                    "reason": reason_skip,
                    "details": details,
                },
            )
            return None

    cleaned_main_html = _clean_html_fragment_for_storage(raw_main_html_from_readability)
    temp_cleaned_soup = BeautifulSoup(cleaned_main_html, "lxml")
    plain_text_from_cleaned_main = temp_cleaned_soup.get_text(separator="\n", strip=True).lower()

    if not plain_text_from_cleaned_main or any(msg in plain_text_from_cleaned_main for msg in soft_error_strings):
        reason_skip = "empty_content_after_cleaning"
        details = {"cleaned_main_text_length": len(plain_text_from_cleaned_main)}
        soft_error_matches = [s for s in soft_error_strings if s in plain_text_from_cleaned_main]
        if soft_error_matches:
            reason_skip = "soft_error_after_cleaning"
            details["soft_errors_matched"] = soft_error_matches

        module_logger.info(
            "Skipped HTML: Content check after cleaning failed",
            extra={
                "event_type": "page_skipped_html",
                "url": response.url,
                "reason": reason_skip,
                "details": details,
            },
        )
        return None

    soup_full_page = BeautifulSoup(response.text, "lxml")
    page_title = page_title_from_readability
    if not page_title:
        h1_tag = soup_full_page.select_one("h1")
        if h1_tag:
            page_title = h1_tag.get_text(strip=True)
    if not page_title:
        title_tag_obj = soup_full_page.select_one("title")
        if title_tag_obj:
            page_title = title_tag_obj.get_text(strip=True)
    if not page_title:
        page_title = "Untitled Page"

    lang = extract_lang_from_url(response.url)
    if lang == "unknown":
        text_for_lang_detect = temp_cleaned_soup.get_text(separator=" ", strip=True)
        if text_for_lang_detect:
            detected_lang_from_html = detect_lang_from_content(text_for_lang_detect)
            if detected_lang_from_html != "unknown":
                lang = detected_lang_from_html

    extracted_page_metadata = extract_metadata(soup_full_page)

    item = RawPageItem(
        url=response.url,
        type="html",
        title=page_title.replace("\x00", ""),
        text=cleaned_main_html.replace("\x00", ""),
        date_scraped=datetime.now(tz).isoformat(),
        date_updated=date_extractor(response.text),
        status=response.status,
        lang=lang,
        metadata_extracted=extracted_page_metadata,
    )

    items_list: List[RawPageItem] = [item]
    embedded_links: List[str] = []

    for a_tag in soup_full_page.find_all("a", href=True):
        href = a_tag.get("href")
        if href and href.lower().endswith((".pdf", ".ics")):
            abs_url = urljoin(response.url, href)
            if abs_url not in embedded_links:
                embedded_links.append(abs_url)

    return items_list, embedded_links

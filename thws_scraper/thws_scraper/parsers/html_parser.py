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


def deobfuscate_text(text: str) -> str:
    """
    Replaces common email obfuscation patterns in a block of text.
    """
    if not text:
        return ""
    return text.replace("[at]", "@").replace(" [@] ", "@").replace(" [at] ", "@")


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
        links=True,
        meta=False,
        page_structure=False,
        processing_instructions=True,
        embedded=True,
        frames=True,
        forms=True,
        annoying_tags=True,
        remove_tags=[
            "noscript",
            "header",
            "footer",
            "nav",
            "dialog",
            "menu",
        ],
        kill_tags=["img", "audio", "video", "svg"],
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

    # This preserves the text content (like emails and phone numbers) while removing the hyperlink itself.
    for a_tag in final_soup.find_all("a"):
        a_tag.unwrap()

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


def _extract_raw_content(soup: BeautifulSoup, response_text: str, url: str) -> Tuple[Optional[str], Optional[str], str]:
    """
    Finds the main content by using a configured Readability instance.
    """
    raw_main_html = None
    page_title = None
    strategy_used = "Readability (configured)"

    try:
        positive_keywords = ["personDetail", "person-indepth"]

        readability_doc = ReadabilityDocument(response_text, positive_keywords=positive_keywords)

        raw_main_html = readability_doc.summary()
        page_title = readability_doc.title()

    except Exception as e:
        strategy_used = "Body Tag Fallback (on error)"
        module_logger.warning(
            "Readability processing failed, falling back to body tag.",
            extra={
                "event_type": "readability_processing_failed",
                "url": url,
                "error": str(e),
                "response_body_preview": response_text[:2000],
            },
        )
        raw_main_html = str(soup.body) if soup.body else ""

    return raw_main_html, page_title, strategy_used


def _finalize_title(current_title: Optional[str], soup: BeautifulSoup) -> str:
    """Finds the best possible title if one hasn't been found yet."""
    if current_title and current_title.strip():
        return current_title

    title_tag = soup.select_one("title")
    if title_tag and title_tag.get_text(strip=True):
        return title_tag.get_text(strip=True)

    return "Untitled Page"


def parse_html(response: Response, soft_error_strings: List[str], tz: ZoneInfo) -> Optional[Tuple[List[RawPageItem], List[str]]]:
    """
    Main coordinator function for parsing HTML pages.
    """
    module_logger.debug("Starting HTML parsing.", extra={"event_type": "html_parsing_started", "url": response.url})
    soup_full_page = BeautifulSoup(response.text, "lxml")

    # 1. Extract main content using the best strategy
    raw_main_html, page_title, strategy_used = _extract_raw_content(soup_full_page, response.text, response.url)

    if not raw_main_html or not raw_main_html.strip():
        module_logger.error(
            "All strategies failed to extract any main HTML content.",
            extra={"event_type": "html_extraction_failed", "url": response.url},
        )
        return None

    # 2. Clean the extracted HTML
    cleaned_main_html = _clean_html_fragment_for_storage(raw_main_html)

    # 3. Deobfuscate emails in the cleaned text
    cleaned_main_html = deobfuscate_text(cleaned_main_html)

    # 4. Validate the cleaned content
    plain_text_from_cleaned_main = BeautifulSoup(cleaned_main_html, "lxml").get_text(strip=True).lower()

    if not plain_text_from_cleaned_main:
        details = {"strategy_used": strategy_used, "raw_html_before_cleaning": raw_main_html}
        module_logger.info(
            "Skipped HTML: Content is empty after cleaning.",
            extra={
                "event_type": "page_skipped_html",
                "reason": "empty_content_after_cleaning",
                "url": response.url,
                "details": details,
            },
        )
        return None

    matched_errors = [s for s in soft_error_strings if s in plain_text_from_cleaned_main]
    if matched_errors:
        details = {"strategy_used": strategy_used, "soft_errors_matched": matched_errors}
        module_logger.info(
            "Skipped HTML: Found soft error string(s) in content.",
            extra={
                "event_type": "page_skipped_html",
                "reason": "soft_error_after_cleaning",
                "url": response.url,
                "details": details,
            },
        )
        return None

    # 5. Finalize page details
    final_title = _finalize_title(page_title, soup_full_page)
    lang = extract_lang_from_url(response.url)
    if lang == "unknown":
        text_for_lang_detect = BeautifulSoup(cleaned_main_html, "lxml").get_text(separator=" ", strip=True)
        if text_for_lang_detect:
            lang = detect_lang_from_content(text_for_lang_detect)

    # 6. Create the Scrapy Item
    item = RawPageItem(
        url=response.url,
        type="html",
        title=final_title.replace("\x00", ""),
        text=cleaned_main_html.replace("\x00", ""),
        date_scraped=datetime.now(tz).isoformat(),
        date_updated=date_extractor(response.text),
        status=response.status,
        lang=lang,
        metadata_extracted=extract_metadata(soup_full_page),
    )

    # 7. Extract embedded links
    embedded_links = [urljoin(response.url, a_tag.get("href")) for a_tag in soup_full_page.find_all("a", href=True) if a_tag.get("href", "").lower().endswith((".pdf", ".ics"))]

    details = {
        "strategy_used": strategy_used,
        "item_title": final_title,
        "text_length": len(cleaned_main_html),
    }
    module_logger.info(
        "Successfully parsed HTML page",
        extra={
            "event_type": "html_parsed_successfully",
            "url": response.url,
            "details": details,
        },
    )
    return [item], list(set(embedded_links))

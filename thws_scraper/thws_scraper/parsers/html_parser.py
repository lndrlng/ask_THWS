import logging
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import urljoin

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

    # Readability already removes a lot of structure like nav, header, footer from its summary.
    cleaner = Cleaner(
        scripts=True,  # Remove <script> tags
        javascript=True,  # Remove JS event handlers (e.g., onclick)
        comments=True,  # Remove comments
        style=True,  # Remove <style> tags and style attributes
        inline_style=True,  # Remove style attributes, equivalent to style=True for attributess
        links=False,  # Keep <link> tags (e.g., canonical, though unlikely in readability's output)
        meta=False,  # Keep <meta> tags (unlikely in readability's output)
        page_structure=False,  # Keep basic structure tags like <div>, <p>
        processing_instructions=True,  # Remove processing instructions
        embedded=True,  # Remove <embed>, <object>
        frames=True,  # Remove <iframe>, <frame>
        forms=False,  # Remove <form> elements (Readability often handles this for main content)
        annoying_tags=True,  # Remove <blink>, <marquee>
        remove_tags=[  # Explicitly remove these if they slip through
            "noscript",
            "header",
            "footer",
            "nav",
            "aside",
            "figure",  # If not containing essential content
            "dialog",
            "menu",
        ],
        kill_tags=None,  # Use remove_tags instead for clarity
        remove_unknown_tags=False,  # Keep unknown tags unless specified
        safe_attrs_only=False,  # We are not relying on a predefined list of safe_attrs
        # Instead, we'll strip specific ones like class, id later.
        # Default safe_attrs includes common ones like href, src, alt.
    )

    try:
        # lxml cleaner expects a string and returns a string
        cleaned_html_lxml = cleaner.clean_html(partially_cleaned_html)
    except Exception as e:
        module_logger.warning(
            f"lxml.html.clean.Cleaner failed: {e}. Falling back to basic BS4 comment removal."
        )
        cleaned_html_lxml = partially_cleaned_html

    # Final pass with BeautifulSoup to remove all 'class' and 'id' attributes,
    # and ensure event handlers are gone.
    final_soup = BeautifulSoup(cleaned_html_lxml, "lxml")
    for tag in final_soup.find_all(True):  # True matches all tags
        # Attributes to remove unconditionally
        for attr_to_remove in ["class", "id", "style"]:  # Style should be gone, but defensive
            if attr_to_remove in tag.attrs:
                del tag.attrs[attr_to_remove]

        # Remove any remaining on* event handlers
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
        if tag and tag.get("content"):
            return tag["content"].strip()
        return None

    metadata["meta_description"] = get_meta_content({"name": "description"})
    metadata["meta_keywords"] = get_meta_content({"name": "keywords"})

    metadata["og_title"] = get_meta_content({"property": "og:title"})
    metadata["og_description"] = get_meta_content({"property": "og:description"})
    metadata["og_type"] = get_meta_content({"property": "og:type"})
    metadata["og_url"] = get_meta_content({"property": "og:url"})

    metadata["article_published_time"] = get_meta_content({"property": "article:published_time"})
    metadata["article_modified_time"] = get_meta_content({"property": "article:modified_time"})

    return metadata


def parse_html(
    response: Response, soft_error_strings: List[str]
) -> Optional[Tuple[List[RawPageItem], List[str]]]:
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
            f"Readability processing failed for {response.url}: {e}. "
            "Attempting fallback to full body for checks."
        )
        soup_full_page_fallback = BeautifulSoup(response.text, "lxml")
        raw_main_html_from_readability = (
            str(soup_full_page_fallback.body) if soup_full_page_fallback.body else response.text
        )
        page_title_from_readability = (
            soup_full_page_fallback.title.string if soup_full_page_fallback.title else ""
        )

    if not raw_main_html_from_readability:
        module_logger.warning(
            f"Readability returned empty main content for {response.url}. "
            "Checking full response text for soft errors."
        )
        # Use full text for soft error check if readability fails to produce content
        # This is important as error pages might be correctly
        # identified by readability as having no "article"
        temp_full_soup = BeautifulSoup(response.text, "lxml")
        plain_text_for_check_full = temp_full_soup.get_text(separator="\n", strip=True).lower()
        if not plain_text_for_check_full or any(
            msg in plain_text_for_check_full for msg in soft_error_strings
        ):
            module_logger.info(
                f"Skipping page {response.url} due to soft error in full text or empty full text "
                "(and Readability yielded no main content)."
            )
            return None
        # If no soft error, but readability was empty, we might proceed with an empty
        # `cleaned_main_html` or log that we're storing a page with potentially no usable text.
        # For now, `cleaned_main_html` will be based on the empty `raw_main_html_from_readability`.

    cleaned_main_html = _clean_html_fragment_for_storage(raw_main_html_from_readability)

    # Perform soft error check on the *cleaned main content*
    temp_cleaned_soup = BeautifulSoup(cleaned_main_html, "lxml")
    plain_text_from_cleaned_main = temp_cleaned_soup.get_text(separator="\n", strip=True).lower()

    if not plain_text_from_cleaned_main or any(
        msg in plain_text_from_cleaned_main for msg in soft_error_strings
    ):
        module_logger.info(
            f"Skipping page {response.url} due to soft error or empty content after cleaning."
        )
        return None

    # Create a full page soup once for metadata, links, and title fallbacks
    soup_full_page = BeautifulSoup(response.text, "lxml")

    # Determine page title: Readability's title > H1 > <title> tag
    page_title = page_title_from_readability
    if not page_title:  # If Readability's title is empty or not good
        h1_tag = soup_full_page.select_one("h1")
        if h1_tag:
            page_title = h1_tag.get_text(strip=True)
    if not page_title:  # Fallback to HTML <title> tag
        title_tag_obj = soup_full_page.select_one("title")
        if title_tag_obj:
            page_title = title_tag_obj.get_text(strip=True)
    if not page_title:
        page_title = "Untitled Page"

    # Language detection
    lang = extract_lang_from_url(response.url)
    if lang == "unknown":
        text_for_lang_detect = temp_cleaned_soup.get_text(separator=" ", strip=True)
        if text_for_lang_detect:
            detected_lang_from_html = detect_lang_from_content(text_for_lang_detect)
            if detected_lang_from_html != "unknown":
                lang = detected_lang_from_html

    # Extract additional metadata
    extracted_page_metadata = extract_metadata(soup_full_page)

    item = RawPageItem(
        url=response.url,
        type="html",
        title=page_title.replace("\x00", ""),
        text=cleaned_main_html.replace("\x00", ""),
        date_scraped=datetime.utcnow().isoformat(),
        date_updated=date_extractor(response.text),  # date_extractor uses full page HTML
        status=response.status,
        lang=lang,
        metadata_extracted=extracted_page_metadata,
    )

    items_list: List[RawPageItem] = [item]
    embedded_links: List[str] = []

    # Extract PDF/ICS links from the *whole page soup*
    for a_tag in soup_full_page.find_all("a", href=True):
        href = a_tag.get("href")
        if href and href.lower().endswith((".pdf", ".ics")):
            abs_url = urljoin(response.url, href)
            if abs_url not in embedded_links:  # Avoid duplicates from the same page
                embedded_links.append(abs_url)

    return items_list, embedded_links

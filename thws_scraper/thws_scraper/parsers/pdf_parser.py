import io
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import fitz
from scrapy.http import Response

from ..items import RawPageItem
from ..utils.lang import detect_lang_from_content, extract_lang_from_url


def parse_pdf(response: Response) -> Optional[RawPageItem]:
    """
    Create a RawPageItem for a PDF, including its raw content.
    Language is detected first from URL, then from extracted text content as a fallback.
    Text extraction from PDF content is for language detection only and not stored in item['text'].
    """
    title_str = urlparse(response.url).path.split("/")[-1]
    metadata_parse_error = None

    lang = extract_lang_from_url(response.url)

    if lang == "unknown":
        pdf_text_for_lang_detect = ""
        try:
            with fitz.open(stream=io.BytesIO(response.body), filetype="pdf") as doc:
                meta = doc.metadata or {}
                pdf_title = meta.get("title", "")
                if pdf_title and isinstance(pdf_title, str) and pdf_title.strip():
                    title_str = pdf_title.strip()

                if lang == "unknown":
                    for page_num in range(len(doc)):
                        page = doc.load_page(page_num)
                        pdf_text_for_lang_detect += page.get_text("text") + " "

                    if pdf_text_for_lang_detect.strip():
                        detected_lang_content = detect_lang_from_content(pdf_text_for_lang_detect)
                        if detected_lang_content != "unknown":
                            lang = detected_lang_content
        except Exception as e:
            metadata_parse_error = f"PyMuPDF metadata or text extraction failed: {str(e)}"

    item = RawPageItem(
        url=response.url,
        type="pdf",
        title=title_str,
        text="",
        file_content=response.body,
        date_scraped=datetime.utcnow().isoformat(),
        date_updated=None,
        status=response.status,
        lang=lang,
        parse_error=metadata_parse_error,
    )
    return item

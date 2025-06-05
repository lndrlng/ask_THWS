import io
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import fitz
from scrapy.http import Response

from ..items import RawPageItem
from ..utils.lang import extract_lang_from_url


def parse_pdf(response: Response) -> Optional[RawPageItem]:
    """
    Create a RawPageItem for a PDF, including its raw content.
    Text extraction is REMOVED.
    """
    title_str = urlparse(response.url).path.split("/")[-1]
    metadata_parse_error = None

    try:
        with fitz.open(stream=io.BytesIO(response.body), filetype="pdf") as doc:
            meta = doc.metadata or {}
            pdf_title = meta.get("title", "")
            if pdf_title and isinstance(pdf_title, str) and pdf_title.strip():
                title_str = pdf_title.strip()
    except Exception as e:
        metadata_parse_error = f"PyMuPDF metadata extraction failed: {str(e)}"

    lang = extract_lang_from_url(response.url)

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

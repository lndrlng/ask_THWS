import os
import sys
import logging
from typing import Dict, Any

import fitz  # PyMuPDF
from markdownify import markdownify as md
from langchain.docstore.document import Document

log = logging.getLogger(__name__)


def init_worker():
    """
    This function is run once by each worker process when it's created.
    It redirects the process's standard error output to a null device,
    which effectively silences all low-level C-library errors from MuPDF.
    """
    sys.stderr = open(os.devnull, "w")


def extract_text_from_pdf(pdf_bytes: bytes, url: str) -> str:
    """Extracts text from a PDF's bytes using PyMuPDF."""
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            text = "".join(page.get_text() for page in doc)

        if not text.strip():
            raise ValueError("PDF is valid but contains no text.")

        return text.replace("\n", " ").strip()
    except Exception:
        log.error(f"Broken PDF, failed to process: {url}")
        return ""


def process_document_content(doc_data: Dict[str, Any]) -> Document | None:
    """
    Takes a dictionary containing raw document data, processes its content
    (HTML->Markdown, PDF->Text), and returns a LangChain Document.
    """
    metadata = doc_data.get("metadata", {})
    page_content = doc_data.get("page_content", "")
    doc_type = metadata.get("type")

    if doc_type == "html" and page_content:
        try:
            page_content = md(page_content, heading_style="ATX").strip()
        except Exception as e:
            log.error(f"Failed to convert HTML to Markdown for url: {metadata.get('url')}: {e}")
            page_content = ""

    elif doc_type == "pdf":
        pdf_bytes = doc_data.get("pdf_bytes")
        if pdf_bytes:
            page_content = extract_text_from_pdf(pdf_bytes, metadata.get("url", "unknown"))

    if not page_content:
        return None

    return Document(page_content=page_content.replace("\x00", ""), metadata=metadata)
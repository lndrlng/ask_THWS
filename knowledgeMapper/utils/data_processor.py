import os
import sys
import logging
from typing import Dict, Any

import fitz 
from markdownify import markdownify as md  
from langchain.docstore.document import Document

log = logging.getLogger(__name__)

def init_worker():
    """
    Worker process initializer: 
    Redirects stderr to null, which suppresses noisy C-library warnings/errors 
    from MuPDF (used by PyMuPDF) that would otherwise clutter the logs.
    """
    sys.stderr = open(os.devnull, "w")

def extract_text_from_pdf(pdf_bytes: bytes, url: str) -> str:
    """
    Extracts all text from a PDF file in-memory (provided as bytes).
    Uses PyMuPDF (fitz), which is robust and works even with tricky files.
    - Returns the text as a single string (all pages concatenated, newlines replaced by spaces).
    - If the PDF is empty or cannot be processed, logs an error and returns an empty string.
    """
    try:
        # Open the PDF from bytes and concatenate text from all pages
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            text = "".join(page.get_text() for page in doc)

        # If there's no text at all, treat as a "broken" or scanned PDF
        if not text.strip():
            raise ValueError("PDF is valid but contains no text.")

        # Return single-line, cleaned text (strip leading/trailing whitespace)
        return text.replace("\n", " ").strip()
    except Exception:
        log.error(f"Broken PDF, failed to process: {url}")
        return ""

def process_document_content(doc_data: Dict[str, Any]) -> Document | None:
    """
    Main content processing function:
    Takes a dict of raw document data, determines type, 
    and converts the content to Markdown (for HTML) or plain text (for PDF).
    Returns a LangChain Document object if successful, or None if empty/broken.
    """
    metadata = doc_data.get("metadata", {})
    page_content = doc_data.get("page_content", "")
    doc_type = metadata.get("type")

    # If HTML, convert to Markdown using markdownify.
    if doc_type == "html" and page_content:
        try:
            page_content = md(page_content, heading_style="ATX").strip()
        except Exception as e:
            log.error(f"Failed to convert HTML to Markdown for url: {metadata.get('url')}: {e}")
            page_content = ""

    # If PDF, extract text from file bytes.
    elif doc_type == "pdf":
        pdf_bytes = doc_data.get("pdf_bytes")
        if pdf_bytes:
            page_content = extract_text_from_pdf(pdf_bytes, metadata.get("url", "unknown"))

    # If content is still empty, skip this document.
    if not page_content:
        return None

    # Replace any embedded NULL characters (can occur from buggy extractions)
    return Document(page_content=page_content.replace("\x00", ""), metadata=metadata)

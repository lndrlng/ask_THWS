import os
import sys
import logging
import concurrent.futures
from typing import List, Dict, Any

from pymongo import MongoClient
from gridfs import GridFS
from langchain.docstore.document import Document

import config  
from .data_processor import process_document_content, init_worker


log = logging.getLogger(__name__)


def pre_process_and_load_content(mongo_doc: Dict, fs: GridFS) -> Dict | None:
    """
    Prepares a single document by fetching its content from GridFS if necessary.
    """
    doc_type = mongo_doc.get("type")
    # Accept HTML, PDF, or iCal
    if not (mongo_doc.get("text") or mongo_doc.get("gridfs_id") or mongo_doc.get("file_content")):
        return None

    page_content = ""
    file_bytes = None

    # HTML: just take the text
    if doc_type == "html":
        page_content = mongo_doc.get("text", "")
    # PDF or iCal: try to load file content from GridFS or field
    elif doc_type in {"pdf", "ical"}:
        if mongo_doc.get("gridfs_id"):
            try:
                gridfs_file = fs.get(mongo_doc["gridfs_id"])
                file_bytes = gridfs_file.read()
            except Exception as e:
                log.warning(f"Could not read GridFS file for url {mongo_doc.get('url')}: {e}")
        elif mongo_doc.get("file_content"):
            file_bytes = mongo_doc.get("file_content")

    # If no content, try to fallback to plain text
    if not page_content and not file_bytes and mongo_doc.get("text"):
        page_content = mongo_doc.get("text")

    # Build unified metadata
    metadata = {
        "source_db": "mongodb",
        "mongo_id": str(mongo_doc.get("_id")),
        "url": mongo_doc.get("url", "unknown_url"),
        "title": mongo_doc.get("title", ""),
        "type": mongo_doc.get("type", "unknown"),
        "date_scraped": mongo_doc.get("date_scraped"),
        "lang": str(mongo_doc.get("lang", "unknown")),
    }

    # Pick key for file bytes based on doc_type for downstream logic
    result = {
        "page_content": page_content,
        "pdf_bytes" if doc_type == "pdf" else "ical_bytes" if doc_type == "ical" else "file_bytes": file_bytes,
        "metadata": metadata,
    }
    # Remove file_bytes key if None (avoid confusing process_document_content)
    if not file_bytes:
        if "pdf_bytes" in result: result.pop("pdf_bytes")
        if "ical_bytes" in result: result.pop("ical_bytes")
        if "file_bytes" in result: result.pop("file_bytes")
    return result


def load_documents_from_mongo() -> List[Document]:
    """
    Connects to MongoDB using settings from config.py, pre-loads all data,
    and uses a process pool to call the external processing function.
    """
    client = MongoClient(
        f"mongodb://{config.MONGO_USER}:{config.MONGO_PASS}@{config.MONGO_HOST}:{config.MONGO_PORT}/{config.MONGO_DB_NAME}?authSource=admin"
    )
    db = client[config.MONGO_DB_NAME]
    fs = GridFS(db)

    log.info("Fetching document list from MongoDB...")
    all_mongo_docs = list(db[config.MONGO_PAGES_COLLECTION].find())
    all_mongo_docs.extend(list(db[config.MONGO_FILES_COLLECTION].find({"type": {"$in": ["pdf", "ical"]}})))
    log.info(f"Found {len(all_mongo_docs)} total document references.")

    log.info("Pre-loading raw content from GridFS...")
    docs_to_process = []
    for doc in all_mongo_docs:
        processed_doc = pre_process_and_load_content(doc, fs)
        if processed_doc:
            docs_to_process.append(processed_doc)
    client.close()
    log.info(f"Prepared {len(docs_to_process)} valid documents for processing.")

    # Language filter
    if hasattr(config, "LANGUAGE") and config.LANGUAGE != "all":
        docs_to_process = [
            doc for doc in docs_to_process
            if doc.get("metadata", {}).get("lang", "unknown").lower() == config.LANGUAGE
        ]
        log.info(f"Filtered to language '{config.LANGUAGE}': {len(docs_to_process)} remain.")

    if not docs_to_process:
        return []

    log.info("Dispatching processing to worker pool...")

    with concurrent.futures.ProcessPoolExecutor(
        max_workers=os.cpu_count(),
        initializer=init_worker
    ) as executor:
        results = executor.map(process_document_content, docs_to_process)
        langchain_docs = [doc for doc in results if doc is not None]

    log.info(f"Successfully loaded and processed {len(langchain_docs)} documents in parallel.")
    return langchain_docs

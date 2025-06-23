import os
import sys
import logging
import concurrent.futures
from typing import List, Dict, Any

from pymongo import MongoClient
from gridfs import GridFS
from langchain.docstore.document import Document

from data_processor import process_document_content, init_worker

log = logging.getLogger(__name__)


MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
MONGO_PORT = int(os.getenv("MONGO_PORT", 27017))
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "askthws_scraper")
MONGO_USER = os.getenv("MONGO_USER", "scraper")
MONGO_PASS = os.getenv("MONGO_PASS", "password")
MONGO_PAGES_COLLECTION = os.getenv("MONGO_PAGES_COLLECTION", "pages")
MONGO_FILES_COLLECTION = os.getenv("MONGO_FILES_COLLECTION", "files")


def pre_process_and_load_content(mongo_doc: Dict, fs: GridFS) -> Dict | None:
    """
    Prepares a single document by fetching its content from GridFS if necessary.
    This runs in the main process.
    """
    doc_type = mongo_doc.get("type")

    if not (mongo_doc.get("text") or mongo_doc.get("gridfs_id") or mongo_doc.get("file_content")):
        return None

    page_content = ""
    pdf_bytes = None

    if doc_type == "html":
        page_content = mongo_doc.get("text", "")
    elif doc_type == "pdf":
        if mongo_doc.get("gridfs_id"):
            try:
                gridfs_file = fs.get(mongo_doc["gridfs_id"])
                pdf_bytes = gridfs_file.read()
            except Exception as e:
                log.warning(f"Could not read GridFS file for url {mongo_doc.get('url')}: {e}")
        elif mongo_doc.get("file_content"):
            pdf_bytes = mongo_doc.get("file_content")

    if not page_content and not pdf_bytes and mongo_doc.get("text"):
        page_content = mongo_doc.get("text")

    return {
        "page_content": page_content,
        "pdf_bytes": pdf_bytes,
        "metadata": {
            "source_db": "mongodb",
            "mongo_id": str(mongo_doc.get("_id")),
            "url": mongo_doc.get("url", "unknown_url"),
            "title": mongo_doc.get("title"),
            "type": mongo_doc.get("type"),
            "date_scraped": mongo_doc.get("date_scraped"),
            "lang": mongo_doc.get("lang"),
        },
    }


def load_documents_from_mongo() -> List[Document]:
    """
    Connects to MongoDB, pre-loads all data, and uses a process pool
    to call the external processing function.
    """
    client = MongoClient(
        f"mongodb://{MONGO_USER}:{MONGO_PASS}@{MONGO_HOST}:{MONGO_PORT}/{MONGO_DB_NAME}?authSource=admin"
    )
    db = client[MONGO_DB_NAME]
    fs = GridFS(db)

    log.info("Fetching document list from MongoDB...")
    all_mongo_docs = list(db[MONGO_PAGES_COLLECTION].find())
    all_mongo_docs.extend(list(db[MONGO_FILES_COLLECTION].find({"type": "pdf"})))
    log.info(f"Found {len(all_mongo_docs)} total document references.")

    log.info("Pre-loading raw content from GridFS...")
    docs_to_process = []
    for doc in all_mongo_docs:
        processed_doc = pre_process_and_load_content(doc, fs)
        if processed_doc:
            docs_to_process.append(processed_doc)
    client.close()
    log.info(f"Prepared {len(docs_to_process)} valid documents for processing.")

    if not docs_to_process:
        return []

    langchain_docs = []
    log.info("Dispatching processing to worker pool...")

    with concurrent.futures.ProcessPoolExecutor(
        max_workers=os.cpu_count(),
        initializer=init_worker  
    ) as executor:
        results = executor.map(process_document_content, docs_to_process)

        langchain_docs = [doc for doc in results if doc is not None]

    log.info(f"Successfully loaded and processed {len(langchain_docs)} documents in parallel.")
    return langchain_docs


if __name__ == "__main__":
    documents = load_documents_from_mongo()
    log.info(f"Finished. Total documents loaded: {len(documents)}")
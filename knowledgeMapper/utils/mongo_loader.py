import os
import sys
import logging
import concurrent.futures
from typing import List, Dict, Any, Tuple
from collections import defaultdict

from pymongo import MongoClient
from gridfs import GridFS
from langchain.docstore.document import Document

import config
from .data_processor import process_document_content, init_worker
from .subdomain_utils import get_sanitized_subdomain 

log = logging.getLogger(__name__)

def load_documents_from_mongo() -> List[Document]:
    """
    Connects to MongoDB and performs an EFFICIENT HYBRID data load,
    logging a per-subdomain breakdown at the end.
    """
    client = MongoClient(
        f"mongodb://{config.MONGO_USER}:{config.MONGO_PASS}@{config.MONGO_HOST}:{config.MONGO_PORT}/{config.MONGO_DB_NAME}?authSource=admin"
    )
    db = client[config.MONGO_DB_NAME]
    fs = GridFS(db)
    final_docs = []
    
    stats = {"from_cache": 0, "live_processed": 0}
    by_subdomain = defaultdict(int)

    lang_filter = {}
    if config.LANGUAGE != "all":
        log.info(f"Filtering all queries for language: '{config.LANGUAGE}'")
        lang_filter = {"lang": config.LANGUAGE}

    # --- 1. Load Pre-processed PDFs and count subdomains ---
    log.info(f"Loading pre-processed PDF data from '{config.MONGO_EXTRACTED_CONTENT_COLLECTION}'...")
    extracted_collection = db[config.MONGO_EXTRACTED_CONTENT_COLLECTION]
    pdf_filter = {}
    if config.LANGUAGE != "all":
        pdf_filter = {"source_metadata.lang": config.LANGUAGE}
    
    for doc_data in extracted_collection.find(pdf_filter):
        metadata = doc_data.get("source_metadata", {})
        url = doc_data.get("source_url")
        metadata["url"] = url
        doc = Document(page_content=doc_data.get("extracted_text", ""), metadata=metadata)
        final_docs.append(doc)
        
        subdomain = get_sanitized_subdomain(url)
        by_subdomain[subdomain] += 1
        
    stats["from_cache"] = len(final_docs)
    log.info(f"Loaded {stats['from_cache']} preprocessed PDF documents.")

    # --- 2. Load Raw HTML/iCal and count subdomains ---
    log.info("Fetching raw HTML and iCal documents...")
    html_docs_raw = list(db[config.MONGO_PAGES_COLLECTION].find(lang_filter))
    ical_filter = {"type": "ical", **lang_filter}
    ical_docs_raw = list(db[config.MONGO_FILES_COLLECTION].find(ical_filter))
    
    docs_to_process_live = []
    for doc in html_docs_raw:
        # Count this document's subdomain
        subdomain = get_sanitized_subdomain(doc.get("url"))
        by_subdomain[subdomain] += 1
        docs_to_process_live.append({"page_content": doc.get("text", ""),"metadata": {"type": "html","url": doc.get("url"),"lang": doc.get("lang"),"title": doc.get("title"),},})
        
    for doc in ical_docs_raw:
        # Count this document's subdomain
        subdomain = get_sanitized_subdomain(doc.get("url"))
        by_subdomain[subdomain] += 1
        ical_bytes = (fs.get(doc["gridfs_id"]).read() if doc.get("gridfs_id") else doc.get("file_content"))
        if ical_bytes:
            docs_to_process_live.append({"ical_bytes": ical_bytes,"metadata": {"type": "ical","url": doc.get("url"),"lang": doc.get("lang"),"title": doc.get("title"),},})
    
    client.close()
    
    # --- 3. Process Raw Docs in Parallel ---
    if docs_to_process_live:
        log.info(f"Processing {len(docs_to_process_live)} HTML/iCal documents in parallel...")
        with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count(), initializer=init_worker) as executor:
            live_results = executor.map(process_document_content, docs_to_process_live)
            processed_live_docs = [doc for doc in live_results if doc is not None]
            final_docs.extend(processed_live_docs)
            stats["live_processed"] = len(processed_live_docs)
            log.info(f"Successfully processed {stats['live_processed']} HTML/iCal documents.")

    log.info("--- Data Loading Complete: Breakdown by Subdomain ---")
    sorted_subdomains = sorted(by_subdomain.items(), key=lambda item: item[1], reverse=True)
    for subdomain, count in sorted_subdomains:
        log.info(f"  - {subdomain}: {count} documents")
    log.info("-" * 50)
    
    log.info(f"Total documents loaded and ready for indexing: {len(final_docs)}")
    
    stats["by_subdomain"] = by_subdomain
    return final_docs, stats
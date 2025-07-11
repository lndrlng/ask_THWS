import io
import os
import re
import time
import logging
from datetime import datetime
from pymongo import MongoClient
from gridfs import GridFS
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
from pytesseract import Output
import concurrent.futures

import config

from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.logging import RichHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)
log = logging.getLogger("rich")

TESSERACT_LANG_MAP = {"de": "deu", "en": "eng"}
DEFAULT_OCR_LANG = "deu"
MIN_TEXT_LENGTH_FOR_OCR_FALLBACK = 250

client, db, fs, extracted_collection = None, None, None, None


def init_worker(db_config: dict):
    """Initializer for each worker process."""
    global client, db, fs, extracted_collection
    worker_pid = os.getpid()
    log.debug(f"Initializing worker process with PID: {worker_pid}...")
    try:
        client = MongoClient(
            f"mongodb://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['db_name']}?authSource=admin"
        )
        client.admin.command("ping")
        db = client[db_config["db_name"]]
        fs = GridFS(db)
        extracted_collection = db[db_config["extracted_collection"]]
        log.debug(f"Worker {worker_pid} successfully connected to MongoDB.")
    except Exception:
        log.error(f"Worker {worker_pid} failed to connect to MongoDB.", exc_info=True)
        client = None


def extract_hybrid_text_from_pdf(
    pdf_bytes: bytes, url: str, ocr_lang: str
) -> tuple[str, bool, int, float | None]:
    """
    Performs hybrid text extraction on a PDF using the specified language for OCR.
    """
    full_text = ""
    ocr_was_used = False
    avg_confidence = None
    page_count = 0

    try:
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_count = len(pdf_doc)

        for page in pdf_doc:
            full_text += page.get_text("text")

        if len(full_text.strip()) < MIN_TEXT_LENGTH_FOR_OCR_FALLBACK:
            log.info(f"Minimal text in '{url}'. Falling back to OCR with lang='{ocr_lang}'.")
            ocr_was_used = True
            ocr_texts, confidences = [], []

            for page in pdf_doc:
                pix = page.get_pixmap(dpi=300)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                ocr_data = pytesseract.image_to_data(img, lang=ocr_lang, output_type=Output.DICT)

                page_text = ""
                for j, conf_str in enumerate(ocr_data["conf"]):
                    conf = int(conf_str)
                    if conf > -1:
                        word = ocr_data["text"][j]
                        if word.strip():
                            page_text += word + " "
                            confidences.append(conf)
                ocr_texts.append(page_text)

            if confidences:
                avg_confidence = sum(confidences) / len(confidences)
            full_text = "\n\n--- Page Break ---\n\n".join(ocr_texts)

        return full_text.strip(), ocr_was_used, page_count, avg_confidence

    except Exception as e:
        log.error(f"Failed to process PDF {url}: {e}", exc_info=True)
        return "", False, 0, None


def process_and_insert_single_document(doc: dict) -> dict:
    """
    Processes a single document using the globally available DB connection.
    """
    start_time = time.time()

    if client is None:
        log.error("Database client not initialized in this worker. Cannot process document.")
        return {"status": "fail", "ocr_used": False, "reason": "DB Connection failed"}

    doc_id = doc["_id"]
    url = doc.get("url", "Unknown URL")
    doc_lang_code = doc.get("lang", "").lower()
    ocr_lang_code = TESSERACT_LANG_MAP.get(doc_lang_code, DEFAULT_OCR_LANG)

    try:
        pdf_bytes = None
        if doc.get("gridfs_id"):
            pdf_bytes = fs.get(doc["gridfs_id"]).read()
        elif doc.get("file_content"):
            pdf_bytes = doc.get("file_content")

        if not pdf_bytes:
            return {"status": "fail", "ocr_used": False}

        source_doc_properties = {}
        with fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf") as pdf_file:
            source_doc_properties = pdf_file.metadata or {}

        clean_text, ocr_used, page_count, avg_confidence = extract_hybrid_text_from_pdf(
            pdf_bytes, url, ocr_lang_code
        )

        if clean_text:
            storage_doc = {
                "source_doc_id": doc_id,
                "source_collection": config.MONGO_FILES_COLLECTION,
                "source_url": url,
                "source_metadata": {
                    "title": doc.get("title"),
                    "lang": doc.get("lang"),
                    "type": doc.get("type"),
                    "author": source_doc_properties.get("author"),
                    "creator_tool": source_doc_properties.get("creator"),
                    "creation_date": source_doc_properties.get("creationDate"),
                    "mod_date": source_doc_properties.get("modDate"),
                },
                "extracted_text": clean_text,
                "extracted_at": datetime.utcnow(),
                "processing_metadata": {
                    "ocr_used": ocr_used,
                    "avg_ocr_confidence": (
                        round(avg_confidence, 2) if avg_confidence is not None else None
                    ),
                    "extraction_duration_s": round(time.time() - start_time, 2),
                    "page_count": page_count,
                    "character_count": len(clean_text),
                    "word_count": len(clean_text.split()),
                    "sentence_count": len(re.findall(r"[.!?]+", clean_text)),
                },
            }
            extracted_collection.insert_one(storage_doc)
            return {"status": "success", "ocr_used": ocr_used}
    except Exception:
        log.error(f"Unhandled failure in worker for URL: {url}", exc_info=True)

    return {"status": "fail", "ocr_used": False}


def main():
    log.info("Starting Hybrid Content Extraction...")

    main_client = MongoClient(
        f"mongodb://{config.MONGO_USER}:{config.MONGO_PASS}@{config.MONGO_HOST}:{config.MONGO_PORT}/{config.MONGO_DB_NAME}?authSource=admin"
    )
    main_db = main_client[config.MONGO_DB_NAME]
    source_collection = main_db[config.MONGO_FILES_COLLECTION]
    main_extracted_collection = main_db[config.MONGO_EXTRACTED_CONTENT_COLLECTION]

    log.info(
        f"Ensuring index on target collection '{config.MONGO_EXTRACTED_CONTENT_COLLECTION}'..."
    )
    main_extracted_collection.create_index("source_doc_id", unique=True)

    log.info("Finding unprocessed documents...")
    cached_ids = {
        doc["source_doc_id"] for doc in main_extracted_collection.find({}, {"source_doc_id": 1})
    }
    log.info(f"Found {len(cached_ids)} documents that are already extracted.")

    query = {"type": "pdf", "_id": {"$nin": list(cached_ids)}}

    total_docs = source_collection.count_documents(query)

    if not total_docs:
        log.info("✅ All PDF documents are already extracted. Exiting.")
        main_client.close()
        return

    log.info(f"Found {total_docs} new PDF documents to process. Starting parallel extraction...")

    docs_to_process_cursor = source_collection.find(query)

    successful_inserts, ocr_fallbacks, failures = 0, 0, 0

    progress_columns = [
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[bold blue]{task.completed}/{task.total}"),
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
    ]

    db_config = {
        "user": config.MONGO_USER,
        "password": config.MONGO_PASS,
        "host": config.MONGO_HOST,
        "port": config.MONGO_PORT,
        "db_name": config.MONGO_DB_NAME,
        "extracted_collection": config.MONGO_EXTRACTED_CONTENT_COLLECTION,
    }

    with Progress(*progress_columns) as progress:
        main_task = progress.add_task("[green]Extracting Content...", total=total_docs)

        with concurrent.futures.ProcessPoolExecutor(
            max_workers=os.cpu_count(), initializer=init_worker, initargs=(db_config,)
        ) as executor:
            future_to_doc = {
                executor.submit(process_and_insert_single_document, doc): doc
                for doc in docs_to_process_cursor
            }

            main_client.close()
            log.info("Main database connection closed. Workers will continue processing.")

            for future in concurrent.futures.as_completed(future_to_doc):
                result = future.result()
                if result and result.get("status") == "success":
                    successful_inserts += 1
                    if result.get("ocr_used"):
                        ocr_fallbacks += 1
                else:
                    failures += 1

                ocr_percentage = (
                    (ocr_fallbacks / successful_inserts * 100) if successful_inserts > 0 else 0
                )

                progress.update(
                    main_task,
                    advance=1,
                    description=(
                        f"[green]Extracting... [cyan]OCR: {ocr_fallbacks} ({ocr_percentage:.1f}%)"
                        f"[/] | [red]Fails: {failures}[/]"
                    ),
                )

    log.info(f"✅ Finished content extraction process.")
    log.info(f"    Successfully processed: {successful_inserts}")
    log.info(f"    Required OCR Fallback: {ocr_fallbacks} ({ocr_percentage:.1f}%)")
    log.info(f"    Failures: {failures}")


if __name__ == "__main__":
    main()

import io
import os
import logging
from datetime import datetime
from tqdm import tqdm
from pymongo import MongoClient
from gridfs import GridFS
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
import concurrent.futures

import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

def extract_hybrid_text_from_pdf(pdf_bytes: bytes, url: str) -> str:
    """
    Performs hybrid text extraction on a PDF.
    """
    full_text = ""
    try:
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in pdf_doc:
            full_text += page.get_text("text")
        
        if len(full_text.strip()) < 250:
            log.info(f"Minimal text found in {url}. Falling back to OCR.")
            ocr_texts = []
            for page_num in range(len(pdf_doc)):
                page = pdf_doc.load_page(page_num)
                pix = page.get_pixmap(dpi=300)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                page_text = pytesseract.image_to_string(img, lang='deu')
                ocr_texts.append(page_text)
            full_text = "\n\n--- Page Break ---\n\n".join(ocr_texts)

        return full_text.strip()
        
    except Exception as e:
        log.error(f"Failed to process PDF {url}: {e}", exc_info=True)
        return ""

def process_and_insert_single_document(doc: dict) -> bool:
    """
    Worker function that processes a single PDF and inserts the result directly into MongoDB.
    Returns True on success, False on failure.
    """
    # Each worker process gets its own database connection
    client = MongoClient(
        f"mongodb://{config.MONGO_USER}:{config.MONGO_PASS}@{config.MONGO_HOST}:{config.MONGO_PORT}/{config.MONGO_DB_NAME}?authSource=admin"
    )
    db = client[config.MONGO_DB_NAME]
    fs = GridFS(db)
    extracted_collection = db[config.MONGO_EXTRACTED_CONTENT_COLLECTION]

    doc_id = doc['_id']
    url = doc.get("url", "Unknown URL")
    
    pdf_bytes = None
    if doc.get("gridfs_id"):
        try:
            pdf_bytes = fs.get(doc["gridfs_id"]).read()
        except Exception as e:
            log.warning(f"Worker could not read GridFS file for url {url}: {e}")
            client.close()
            return False
    elif doc.get("file_content"):
        pdf_bytes = doc.get("file_content")
        
    if not pdf_bytes:
        client.close()
        return False
        
    clean_text = extract_hybrid_text_from_pdf(pdf_bytes, url)
    
    if clean_text:
        storage_doc = {
            "source_doc_id": doc_id,
            "source_collection": config.MONGO_FILES_COLLECTION,
            "source_url": url,
            "source_metadata": {
                "title": doc.get("title"), "lang": doc.get("lang"), "type": doc.get("type"),
            },
            "extracted_text": clean_text,
            "extracted_at": datetime.utcnow(),
        }
        extracted_collection.insert_one(storage_doc)
        client.close()
        return True
    
    client.close()
    return False

def main():
    """
    Connects to MongoDB, finds unprocessed PDFs, and processes them in parallel,
    with each worker saving its own result.
    """
    log.info("Starting Hybrid Content Extraction...")
    
    client = MongoClient(
        f"mongodb://{config.MONGO_USER}:{config.MONGO_PASS}@{config.MONGO_HOST}:{config.MONGO_PORT}/{config.MONGO_DB_NAME}?authSource=admin"
    )
    db = client[config.MONGO_DB_NAME]
    
    source_collection = db[config.MONGO_FILES_COLLECTION]
    extracted_collection = db[config.MONGO_EXTRACTED_CONTENT_COLLECTION]

    log.info(f"Ensuring index on target collection '{config.MONGO_EXTRACTED_CONTENT_COLLECTION}'...")
    extracted_collection.create_index("source_doc_id", unique=True)

    # Find PDFs that haven't been processed yet
    cached_ids = {doc['source_doc_id'] for doc in extracted_collection.find({}, {'source_doc_id': 1})}
    docs_to_process = list(source_collection.find({"type": "pdf", "_id": {"$nin": list(cached_ids)}}))
    
    if not docs_to_process:
        log.info("✅ All PDF documents are already extracted. Exiting.")
        client.close()
        return

    log.info(f"Found {len(docs_to_process)} new PDF documents to process. Starting parallel extraction...")
    client.close()

    successful_inserts = 0
    with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        future_to_doc = {executor.submit(process_and_insert_single_document, doc): doc for doc in docs_to_process}
        
        for future in tqdm(concurrent.futures.as_completed(future_to_doc), total=len(docs_to_process), desc="Extracting PDF Content"):
            was_successful = future.result()
            if was_successful:
                successful_inserts += 1


    log.info(f"✅ Finished content extraction process. Successfully processed and saved {successful_inserts} new documents.")

if __name__ == "__main__":
    main()
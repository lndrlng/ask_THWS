import os
import io
from typing import List
from pymongo import MongoClient
from gridfs import GridFS
from langchain.docstore.document import Document
import pypdf

# --- MongoDB Configuration ---
MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
MONGO_PORT = int(os.getenv("MONGO_PORT", 27017))
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "scrapy_db")
MONGO_USER = os.getenv("MONGO_USER")
MONGO_PASS = os.getenv("MONGO_PASS")
MONGO_PAGES_COLLECTION = os.getenv("MONGO_PAGES_COLLECTION", "pages")
MONGO_FILES_COLLECTION = os.getenv("MONGO_FILES_COLLECTION", "files")


def extract_text_from_pdf(pdf_bytes: bytes, url: str) -> str:
    """Extracts text content from raw PDF bytes."""
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "".join(page.extract_text() for page in reader.pages)
        return text.replace("\n", " ").strip()
    except Exception as e:
        print(f"   - ⚠️ Could not extract text from PDF '{url}': {e}")
        return ""

def mongo_doc_to_langchain_doc(mongo_doc: dict, fs: GridFS) -> Document | None:
    """
    Converts a document from MongoDB into a LangChain Document object.
    Returns None if the document has no processable content.
    """
    metadata = {
        "source_db": "mongodb",
        "mongo_id": str(mongo_doc.get("_id")),
        "url": mongo_doc.get("url"),
        "title": mongo_doc.get("title"),
        "type": mongo_doc.get("type"),
        "date_scraped": mongo_doc.get("date_scraped"),
        "lang": mongo_doc.get("lang"),
    }

    page_content = ""
    doc_type = mongo_doc.get("type")

    if doc_type == "html":
        page_content = mongo_doc.get("text", "")
    elif doc_type == "pdf":
        pdf_bytes = None
        if mongo_doc.get("gridfs_id"):
            try:
                gridfs_file = fs.get(mongo_doc["gridfs_id"])
                pdf_bytes = gridfs_file.read()
            except Exception as e:
                print(f"   - ⚠️ Could not fetch GridFS file for url {metadata['url']}: {e}")
        elif mongo_doc.get("file_content"):
            pdf_bytes = mongo_doc["file_content"]

        if pdf_bytes:
            page_content = extract_text_from_pdf(pdf_bytes, metadata['url'])

    # Fallback and final check
    if not page_content and mongo_doc.get("text"):
        page_content = mongo_doc.get("text")

    if not page_content:
        print(f"   - ⚠️ Skipping document with no content: {metadata['url']}")
        return None

    return Document(page_content=page_content.replace("\x00", ""), metadata=metadata)

def load_documents_from_mongo() -> List[Document]:
    """
    Main function to connect to MongoDB, fetch all documents from the 'pages'
    and 'files' collections, and return them as a list of LangChain Documents.
    """
    # 1. Connect to MongoDB
    if MONGO_USER and MONGO_PASS:
        uri = f"mongodb://{MONGO_USER}:{MONGO_PASS}@{MONGO_HOST}:{MONGO_PORT}/{MONGO_DB_NAME}?authSource=admin"
    else:
        uri = f"mongodb://{MONGO_HOST}:{MONGO_PORT}/"

    print(f"[*] Connecting to MongoDB at {MONGO_HOST}...")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        print("✅ MongoDB connection successful.")
    except Exception as e:
        print(f"🔥 MongoDB connection failed: {e}")
        return []

    db = client[MONGO_DB_NAME]
    fs = GridFS(db)
    langchain_docs = []

    # 2. Process 'pages' (HTML) collection
    print(f"\n[*] Processing collection: '{MONGO_PAGES_COLLECTION}'...")
    for doc in db[MONGO_PAGES_COLLECTION].find():
        lc_doc = mongo_doc_to_langchain_doc(doc, fs)
        if lc_doc:
            langchain_docs.append(lc_doc)

    # 3. Process 'files' (PDF) collection
    print(f"\n[*] Processing collection: '{MONGO_FILES_COLLECTION}'...")
    for doc in db[MONGO_FILES_COLLECTION].find({"type": "pdf"}):
        lc_doc = mongo_doc_to_langchain_doc(doc, fs)
        if lc_doc:
            langchain_docs.append(lc_doc)

    print(f"\n[*] Successfully loaded and processed {len(langchain_docs)} documents from MongoDB.")
    client.close()
    return langchain_docs
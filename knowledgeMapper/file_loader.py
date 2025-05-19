# file_loader.py

from langchain.schema import Document
from langchain.document_loaders import PyPDFLoader, TextLoader, UnstructuredHTMLLoader
from pathlib import Path
import json


def clean_text(text):
    return text.replace("\n", " ").replace("read more", "").strip()


def load_json(file_path):
    docs = []
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            if "text" in entry:
                content = clean_text(entry["text"])
                metadata = {
                    "source_file": str(file_path),
                    "title": entry.get("title"),
                    "url": entry.get("url"),
                    "type": entry.get("type"),
                    "date_scraped": entry.get("date_scraped"),
                    "status": entry.get("status"),
                }
                docs.append(Document(page_content=content, metadata=metadata))
    return docs


def load_documents(folder):
    docs = []
    for file in Path(folder).glob("*"):
        ext = file.suffix.lower()
        try:
            if ext == ".json":
                docs.extend(load_json(file))
            elif ext == ".pdf":
                docs.extend(PyPDFLoader(str(file)).load())
            elif ext == ".txt":
                docs.extend(TextLoader(str(file)).load())
            elif ext == ".html":
                docs.extend(UnstructuredHTMLLoader(str(file)).load())
        except Exception as e:
            print(f"Error loading {file}: {e}")
    return docs

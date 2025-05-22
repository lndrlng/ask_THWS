"""
file_loader.py – JSON, JSONL, PDF, TXT, HTML loader returning LangChain Documents
"""

import json
from pathlib import Path
from langchain.docstore.document import Document
from langchain.document_loaders import PyPDFLoader, TextLoader, UnstructuredHTMLLoader


# ── helpers ─────────────────────────────────────────────────────────────
def _clean(text: str) -> str:
    return text.replace("\n", " ").replace("read more", "").strip()


def _entry_to_doc(entry: dict, file_path: Path) -> Document | None:
    if "text" not in entry:
        return None
    md = {
        "source_file": str(file_path),
        "title": entry.get("title"),
        "url": entry.get("url"),
        "type": entry.get("type"),
        "date_scraped": entry.get("date_scraped"),
        "status": entry.get("status"),
    }
    return Document(page_content=_clean(entry["text"]), metadata=md)


# ── per-format loaders ──────────────────────────────────────────────────
def load_json(path: Path) -> list[Document]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    entries = data if isinstance(data, list) else [data]
    return [d for e in entries if (d := _entry_to_doc(e, path))]


def load_jsonl(path: Path) -> list[Document]:
    docs = []
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as err:
                print(f"⚠️  {path}:{ln} bad JSON: {err}")
                continue
            if doc := _entry_to_doc(entry, path):
                docs.append(doc)
    return docs


# ── master dispatcher ───────────────────────────────────────────────────
def load_documents(folder: str | Path) -> list[Document]:
    docs: list[Document] = []
    for fp in Path(folder).glob("*"):
        ext = fp.suffix.lower()
        try:
            if ext == ".json":
                docs.extend(load_json(fp))
            elif ext in (".jsonl", ".ndjson"):
                docs.extend(load_jsonl(fp))
            elif ext == ".pdf":
                docs.extend(PyPDFLoader(str(fp)).load())
            elif ext == ".txt":
                docs.extend(TextLoader(str(fp)).load())
            elif ext == ".html":
                docs.extend(UnstructuredHTMLLoader(str(fp)).load())
        except Exception as exc:
            print(f"Error loading {fp}: {exc}")
    return docs
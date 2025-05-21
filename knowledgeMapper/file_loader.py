import json
from pathlib import Path
from langchain.docstore.document import Document
from langchain.document_loaders import PyPDFLoader, TextLoader, UnstructuredHTMLLoader

# ──────────────────────────────────────────────────────────────
def clean_text(text: str) -> str:
    return text.replace("\n", " ").replace("read more", "").strip()


def _entry_to_document(entry: dict, file_path: Path) -> Document | None:
    """Convert one JSON object to a LangChain Document, or None if no 'text' field."""
    text = entry.get("text")
    if text is None:
        return None

    content = clean_text(text)
    metadata = {
        "source_file": str(file_path),
        "title":        entry.get("title"),
        "url":          entry.get("url"),
        "type":         entry.get("type"),
        "date_scraped": entry.get("date_scraped"),
        "status":       entry.get("status"),
    }
    return Document(page_content=content, metadata=metadata)


# ── JSON ARRAY (.json) ─────────────────────────────────────────
def load_json(file_path: Path) -> list[Document]:
    docs = []
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            doc = _entry_to_document(entry, file_path)
            if doc:  # skip rows without 'text'
                docs.append(doc)
    return docs


# ── JSON-LINES (.jsonl / .ndjson) NEW! ─────────────────────────
def load_jsonl(file_path: Path) -> list[Document]:
    docs = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:                # skip blank lines
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as err:
                print(f"⚠️  {file_path}:{line_no} — bad JSON: {err}")
                continue
            doc = _entry_to_document(entry, file_path)
            if doc:
                docs.append(doc)
    return docs


# ── Master loader ──────────────────────────────────────────────
def load_documents(folder: str | Path) -> list[Document]:
    docs = []
    for file in Path(folder).glob("*"):
        ext = file.suffix.lower()
        try:
            if ext == ".json":
                docs.extend(load_json(file))
            elif ext in (".jsonl", ".ndjson"):
                docs.extend(load_jsonl(file))
            elif ext == ".pdf":
                docs.extend(PyPDFLoader(str(file)).load())
            elif ext == ".txt":
                docs.extend(TextLoader(str(file)).load())
            elif ext == ".html":
                docs.extend(UnstructuredHTMLLoader(str(file)).load())
        except Exception as e:
            print(f"Error loading {file}: {e}")
    return docs

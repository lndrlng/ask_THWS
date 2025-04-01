import json
import sys
import os
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langdetect import detect, DetectorFactory

# Ensure consistent language detection
DetectorFactory.seed = 42

# --- Config Defaults ---
DEFAULT_INPUT = "data/thws_raw.json"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100

# --- CLI Args ---
if len(sys.argv) < 2:
    print(f"Usage: python {sys.argv[0]} <input_file.json>")
    sys.exit(1)

INPUT_PATH = sys.argv[1]
OUTPUT_PATH = os.path.splitext(INPUT_PATH)[0] + "_chunks.json"

# --- Helpers ---

def clean_text(text):
    return " ".join(text.split())

def detect_language(text):
    try:
        return detect(text)
    except:
        return "unknown"

# --- Load raw data ---

with open(INPUT_PATH, "r", encoding="utf-8") as f:
    raw_docs = json.load(f)

# --- Set up chunker ---

splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP
)

chunked_docs = []

# --- Process documents ---

for i, doc in enumerate(raw_docs):
    raw_text = doc.get("text", "")
    if not raw_text.strip():
        continue

    cleaned = clean_text(raw_text)
    lang = detect_language(cleaned)
    chunks = splitter.split_text(cleaned)

    for j, chunk in enumerate(chunks):
        chunked_docs.append({
            "text": chunk,
            "source": doc.get("url"),
            "chunk_id": j,
            "type": doc.get("type"),
            "language": lang
        })

# --- Save output ---

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(chunked_docs, f, indent=2, ensure_ascii=False)

print(f"✅ Saved {len(chunked_docs)} chunks to {OUTPUT_PATH}")

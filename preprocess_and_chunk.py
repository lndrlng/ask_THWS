import json
import sys
import os
import uuid
from langchain.text_splitter import RecursiveCharacterTextSplitter
from tqdm import tqdm
from tqdm import tqdm
from langdetect import detect, DetectorFactory

# make langdetect deterministic
# make langdetect deterministic
DetectorFactory.seed = 42


def main():
    if len(sys.argv) < 2:
        print("❌ Usage: python preprocess_and_chunk.py <input_file.json>")
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("❌ Usage: python preprocess_and_chunk.py <input_file.json>")
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("❌ Usage: python preprocess_and_chunk.py <input_file.json>")
        sys.exit(1)

    input_path = sys.argv[1]
    if not os.path.isfile(input_path):
        print(f"❌ File not found: {input_path}")
        sys.exit(1)

    output_path = input_path.replace(".json", "_chunks.json")

    with open(input_path, "r", encoding="utf-8") as f:
        try:
            raw_docs = json.load(f)
        except json.JSONDecodeError as e:
            print(f"❌ JSON Decode Error: {e}")
            sys.exit(1)

    print(f"🔍 Loaded {len(raw_docs)} documents")

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    input_path = sys.argv[1]
    if not os.path.isfile(input_path):
        print(f"❌ File not found: {input_path}")
        sys.exit(1)

    output_path = input_path.replace(".json", "_chunks.json")

    with open(input_path, "r", encoding="utf-8") as f:
        try:
            raw_docs = json.load(f)
        except json.JSONDecodeError as e:
            print(f"❌ JSON Decode Error: {e}")
            sys.exit(1)

    print(f"🔍 Loaded {len(raw_docs)} documents")

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)

    chunks = []
    chunks = []

    for doc in tqdm(raw_docs, desc="🔄 Chunking"):
        text = doc.get("text", "").strip()
        if not text:
            continue
    for doc in tqdm(raw_docs, desc="🔄 Chunking"):
        text = doc.get("text", "").strip()
        if not text:
            continue

        try:
            lang = detect(text)
        except Exception:
            lang = "unknown"

        metadata = {
            "source": doc.get("url"),
            "title": doc.get("title"),
            "type": doc.get("type"),
            "date_updated": doc.get("date_updated"),
            "lang": lang,
        }

        for chunk_text in splitter.split_text(text):
            chunks.append(
                {
                    "chunk_id": str(uuid.uuid4()),
                    "text": chunk_text,
                    "metadata": metadata,
                }
            )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    print(f"✅ Saved {len(chunks)} chunks → {output_path}")


if __name__ == "__main__":
    main()
    print(f"✅ Saved {len(chunks)} chunks → {output_path}")


if __name__ == "__main__":
    main()

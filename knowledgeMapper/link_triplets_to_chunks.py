import json
from pathlib import Path
from tqdm import tqdm

# === CONFIG ===
CHUNK_FILE = Path("./../data/thws_data_filtered.json")
TRIPLET_FILE = Path("./../data/studiengaenge_triplets.json")
OUTPUT_FILE = Path("./../data/triplets_with_links.json")

# === LOAD FILES ===
with CHUNK_FILE.open("r", encoding="utf-8") as f:
    chunks = json.load(f)

with TRIPLET_FILE.open("r", encoding="utf-8") as f:
    triplets = json.load(f)

# === BUILD LOOKUP: chunk text → metadata
chunk_lookup = {}
for chunk in chunks:
    text = chunk.get("text", "").strip()
    meta = chunk.get("metadata", {})
    chunk_lookup[text] = {
        "chunk_id": chunk.get("chunk_id"),
        "source": meta.get("source"),
        "title": meta.get("title"),
        "type": meta.get("type"),
        "lang": meta.get("lang"),
        "date_updated": meta.get("date_updated")
    }

# === LINK TRIPLETS TO METADATA ===
linked = []

for triplet in tqdm(triplets, desc="🔗 Linking triplets"):
    subj, rel, obj = triplet

    # Try to find which chunk this came from by matching `obj` or `subj` in chunk text
    found = None
    for chunk_text, meta in chunk_lookup.items():
        if subj in chunk_text or obj in chunk_text:
            found = meta
            break

    linked.append({
        "subject": subj,
        "relation": rel,
        "object": obj,
        "source_metadata": found or {}
    })

# === SAVE OUTPUT ===
with OUTPUT_FILE.open("w", encoding="utf-8") as f:
    json.dump(linked, f, ensure_ascii=False, indent=2)

print(f"✅ Linked {len(linked)} triplets → {OUTPUT_FILE}")

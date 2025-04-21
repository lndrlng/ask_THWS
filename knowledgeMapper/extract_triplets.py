import os
import time
import json
import requests
from tqdm import tqdm

from coref import resolve_coreferences
from triplet_utils import (
    load_json, save_json,
    parse_triplets, enrich_with_ner,
    generate_labeled_triplet_with_metadata
)

# === CONFIG ===
INPUT_FILE = "./../data/thws_data_filtered.json"
PROGRESS_FILE = "./../data/studiengaenge_progress.json"
OUTPUT_FILE = "./../data/studiengaenge_triplets.json"
CHUNK_GROUP_SIZE = 2
MAX_TOKENS = 1024
OLLAMA_MODEL = "gemma:7b"

# === Prompt Function ===
def extract_triplets(text):
    prompt = f"""Extrahiere relevante Tripel aus dem folgenden Text im Format (Subjekt, Prädikat, Objekt).
Gib nur Tripel aus. Keine Erklärungen, kein Fließtext.

Beispiel:
(Das Projekt, untersucht, ethische Fragen)
(Die THWS, führt durch, Forschungsinitiative)

Text:
{text}

Tripel:"""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": MAX_TOKENS}
            },
            timeout=30
        )
        response.raise_for_status()
        answer = response.json().get("response")
        return answer.strip() if answer else ""
    except Exception as e:
        print(f"⚠️ No LLM output returned. Error: {e}")
        return ""

# === Load files ===
chunks = load_json(INPUT_FILE)
processed_ids = set(load_json(PROGRESS_FILE)) if os.path.exists(PROGRESS_FILE) else set()
triplets_all = load_json(OUTPUT_FILE) if os.path.exists(OUTPUT_FILE) else []

existing_keys = {(t["subject"], t["relation"], t["object"]) for t in triplets_all if isinstance(t, dict)}

print(f"🔁 Resuming... {len(processed_ids)} chunks already processed.")

# === Main Loop ===
start_time = time.time()

for i in tqdm(range(0, len(chunks), CHUNK_GROUP_SIZE), desc="🔍 Extracting", unit="group"):
    group = chunks[i:i + CHUNK_GROUP_SIZE]
    group_ids = [chunk["chunk_id"] for chunk in group]

    if all(cid in processed_ids for cid in group_ids):
        continue

    combined_text = "\n\n".join(chunk["text"] for chunk in group)
    group_meta = group[0].get("metadata", {}) if group else {}

    try:
        resolved_text = resolve_coreferences(combined_text)
        raw_output = extract_triplets(resolved_text)
        raw_triplets = parse_triplets(raw_output)

        enriched = []
        for subj, pred, obj in raw_triplets:
            triplet = generate_labeled_triplet_with_metadata(subj, pred, obj, group_meta)
            if triplet["confidence"] >= 0.5:
                enriched.append(triplet)

        named_entities = enrich_with_ner(combined_text)
        ner_triplets = [generate_labeled_triplet_with_metadata(ent, "ist erwähnt in", "Studientext", group_meta) for ent in named_entities]

        new_triplets = enriched + ner_triplets
        new_filtered = [
            t for t in new_triplets
            if (t["subject"], t["relation"], t["object"]) not in existing_keys
        ]

        for t in new_filtered:
            existing_keys.add((t["subject"], t["relation"], t["object"]))
        triplets_all.extend(new_filtered)

        save_json(triplets_all, OUTPUT_FILE)
        processed_ids.update(group_ids)
        save_json(list(processed_ids), PROGRESS_FILE)

    except Exception as e:
        print(f"❌ Error in group {group_ids}: {e}")
        continue

duration = time.time() - start_time
print(f"\n✅ Done. {len(triplets_all)} triplets extracted in {duration:.2f} seconds.")

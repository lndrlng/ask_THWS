import os
import time
from tqdm import tqdm
from llama_cpp import Llama

from coref import resolve_coreferences
from triplet_utils import (
    load_json, save_json,
    parse_triplets, enrich_with_ner
)

# === CONFIG ===
INPUT_FILE = "./../data/thws_data_filtered.json"
PROGRESS_FILE = "./../data/studiengaenge_progress.json"
OUTPUT_FILE = "./../data/studiengaenge_triplets.json"
CHUNK_GROUP_SIZE = 2
MAX_TOKENS = 1024
MODEL_PATH = "D:/LLMS/mistral-7b-instruct-v0.2.Q6_K.gguf"

# === INIT LLM ===
print("🚀 Loading LLM model...")
llm = Llama(
    model_path=MODEL_PATH,
    n_ctx=2048,
    n_gpu_layers=30,
    n_threads=8,
    n_batch=128,
    low_vram=True,
    main_gpu=0,
    verbose=False
)
print("✅ LLM loaded.")

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

    output = llm(prompt, max_tokens=MAX_TOKENS, stop=["\n\n", "###"])
    if "choices" in output and output["choices"]:
        return output["choices"][0]["text"].strip()
    else:
        print("⚠️ No LLM output returned.")
        return ""


# === Load files ===
chunks = load_json(INPUT_FILE)
processed_ids = set(load_json(PROGRESS_FILE)) if os.path.exists(PROGRESS_FILE) else set()
triplets_all = load_json(OUTPUT_FILE) if os.path.exists(OUTPUT_FILE) else []

# Convert existing triplets for deduplication
existing_keys = {(t[0], t[1], t[2]) for t in triplets_all if isinstance(t, (list, tuple)) and len(t) >= 3}

print(f"🔁 Resuming... {len(processed_ids)} chunks already processed.")

# === Main Loop ===
start_time = time.time()

for i in tqdm(range(0, len(chunks), CHUNK_GROUP_SIZE), desc="🔍 Extracting", unit="group"):
    group = chunks[i:i + CHUNK_GROUP_SIZE]
    group_ids = [chunk["chunk_id"] for chunk in group]

    # Skip processed chunks
    if all(cid in processed_ids for cid in group_ids):
        continue

    combined_text = "\n\n".join(chunk["text"] for chunk in group)

    # Gather metadata source info
    group_sources = set()
    for chunk in group:
        meta = chunk.get("metadata", {})
        group_sources.add(meta.get("title") or meta.get("source", "Unbekannt"))

    try:
        # === Coref Resolution ===
        resolved_text = resolve_coreferences(combined_text)

        # === Extract Triplets ===
        raw_output = extract_triplets(resolved_text)
        triplets = parse_triplets(raw_output)

        # === NER ===
        named_entities = enrich_with_ner(combined_text)
        ner_triplets = [(ent, "ist erwähnt in", "Studientext") for ent in named_entities]

        # === Metadata Triplets ===
        meta_triplets = []
        for source in group_sources:
            for subj, pred, obj in triplets:
                meta_triplets.append((subj, "kommt aus", source))

        # === Combine & dedupe manually ===
        new_triplets = triplets + ner_triplets + meta_triplets
        new_filtered = [
            t for t in new_triplets
            if (t[0], t[1], t[2]) not in existing_keys
        ]

        # Update sets
        for t in new_filtered:
            existing_keys.add((t[0], t[1], t[2]))
        triplets_all.extend(new_filtered)

        # Save results
        save_json(triplets_all, OUTPUT_FILE)
        processed_ids.update(group_ids)
        save_json(list(processed_ids), PROGRESS_FILE)

    except Exception as e:
        print(f"❌ Error in group {group_ids}: {e}")
        continue

duration = time.time() - start_time
print(f"\n✅ Done. {len(triplets_all)} triplets extracted in {duration:.2f} seconds.")

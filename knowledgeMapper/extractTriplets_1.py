import json
import time
import os
from tqdm import tqdm
from llama_cpp import Llama

# === CONFIG ===
INPUT_FILE = "./../data/thws_data2_chunks.json"
PROGRESS_FILE = "../data/studiengaenge_progress_1.json"
OUTPUT_FILE = "../data/studiengaenge_triplets_1.json"
CHUNK_GROUP_SIZE = 2  # Tune based on your VRAM
MAX_TOKENS = 512

# === Load Model ===
print("🚀 Loading model...")
llm = Llama(
    model_path="D:/LLMS/mistral-7b-instruct-v0.2.Q6_K.gguf",
    n_ctx=2048,
    n_gpu_layers=30,
    n_threads=8,
    n_batch=128,
    low_vram=True,
    main_gpu=0,
    verbose=False
)
print("✅ Model loaded.")

# === Prompt Function ===
def extract_triplets(text):
    prompt = f"""Extrahiere Tripel im Format (Subjekt, Prädikat, Objekt).

Beispiel:
Prof. Kiesewetter startet als Stiftungsprofessorin für das TTZ Bad Kissingen.
(Prof. Kiesewetter, ist, Stiftungsprofessorin)
(Prof. Kiesewetter, arbeitet an, TTZ Bad Kissingen)

{text}
"""
    output = llm(prompt, max_tokens=MAX_TOKENS, stop=["\n\n", "\nText:", "\n###"])
    return output["choices"][0]["text"].strip()

# === Load Data ===
with open(INPUT_FILE, "r", encoding="utf-8") as f:
    chunks = json.load(f)

# Load progress
if os.path.exists(PROGRESS_FILE):
    with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
        processed_ids = set(json.load(f))
else:
    processed_ids = set()

# Load previous output (append mode)
if os.path.exists(OUTPUT_FILE):
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        triplets_all = json.load(f)
else:
    triplets_all = []

print(f"🔁 Resuming... {len(processed_ids)} chunks already processed.")

# === Main Loop ===
start_time = time.time()
for i in tqdm(range(0, len(chunks), CHUNK_GROUP_SIZE), desc="🔍 Extracting", unit="group"):
    group = chunks[i:i + CHUNK_GROUP_SIZE]
    group_ids = [chunk["chunk_id"] for chunk in group]

    # Skip if already processed
    if all(cid in processed_ids for cid in group_ids):
        continue

    # Combine texts
    text_group = "\n\n".join(chunk["text"] for chunk in group)

    try:
        triplets_raw = extract_triplets(text_group)
        lines = [line.strip() for line in triplets_raw.split("\n") if line.strip().startswith("(")]
        triplets_all.extend(lines)

        # Save output incrementally
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(triplets_all, f, indent=2, ensure_ascii=False)

        # Save progress
        processed_ids.update(group_ids)
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(processed_ids), f)

    except Exception as e:
        print(f"❌ Error processing group {group_ids}: {e}")
        continue

# === Done ===
duration = time.time() - start_time
print(f"\n✅ Done. {len(triplets_all)} triplets extracted in {duration:.2f} seconds.")

# === extract_triplets.py (final refined version) ===
import os
import time
from tqdm import tqdm
from coref import resolve_coreferences
from triplet_utils import (
    load_json, save_json, enrich_with_ner, parse_triplets,
    generate_labeled_triplet_with_metadata, score_triplet
)
import spacy
from llama_cpp import Llama

# === CONFIG ===
INPUT_FILE = "./../data/fiw_results_with_ids.json"
OUTPUT_FILE = "./../data/studiengaenge_triplets.json"
PROGRESS_FILE = "./../data/studiengaenge_progress.json"
FILTERED_OUTPUT_FILE = "./../data/studiengaenge_triplets_filtered.json"
MODEL_PATH = "D:/LLMS/mistral-7b-instruct-v0.2.Q6_K.gguf"
CHUNK_GROUP_SIZE = 2
MAX_TOKENS = 1024

print("🚀 Loading models...")
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
nlp = spacy.load("de_core_news_md")
print("✅ Models loaded.")

# === Rule-based SpaCy Triplet Heuristic ===
def spacy_extract_triplets(text):
    doc = nlp(text)
    triplets = []
    for sent in doc.sents:
        subj, pred, obj = None, None, None
        for token in sent:
            if token.dep_ in {"nsubj", "nsubjpass"} and subj is None:
                subj = token.text
            if token.dep_ == "ROOT" and pred is None:
                pred = token.lemma_
            if token.dep_ in {"dobj", "attr", "pobj"} and obj is None:
                obj = token.text
        if subj and pred and obj:
            triplets.append((subj, pred, obj))
    return triplets

# === LLM Triplet Refinement ===
def refine_with_llm(text: str, meta: dict):
    prompt_header = """Extrahiere Tripel im Format (Subjekt, Prädikat, Objekt).
Beispiel:
Prof. Kiesewetter startet als Stiftungsprofessorin für das TTZ Bad Kissingen.
(Prof. Kiesewetter, ist, Stiftungsprofessorin)
(Prof. Kiesewetter, arbeitet an, TTZ Bad Kissingen)
"""
    prompt_footer = "\n\nTripel:"
    max_input_tokens = 2048 - MAX_TOKENS
    max_input_chars = max_input_tokens * 3
    title_hint = f"Titel: {meta.get('title', '')}\n" if 'title' in meta else ""

    doc = nlp(text)
    char_total = 0
    sents = []
    for sent in doc.sents:
        sent_len = len(sent.text)
        if char_total + sent_len > max_input_chars:
            break
        sents.append(sent.text)
        char_total += sent_len
    truncated_text = " ".join(sents)
    final_prompt = f"{prompt_header}{title_hint}{truncated_text}{prompt_footer}"

    try:
        output = llm(final_prompt, max_tokens=MAX_TOKENS, stop=["\n\n", "###"])
        return output["choices"][0]["text"].strip() if "choices" in output else ""
    except Exception as e:
        print(f"❌ LLM refinement failed: {e}")
        return ""

# === NER Entity Validation ===
def is_valid_ner_entity(e: str) -> bool:
    if len(e) < 3 or len(e) > 100:
        return False
    if any(e.lower().startswith(x) for x in ("for example", "please", "known for", "such as", "who", "with whom")):
        return False
    if not any(char.isalpha() for char in e):
        return False
    return True

# === Pipeline ===
chunks = load_json(INPUT_FILE)
processed_ids = set(load_json(PROGRESS_FILE)) if os.path.exists(PROGRESS_FILE) else set()
triplets_all = load_json(OUTPUT_FILE) if os.path.exists(OUTPUT_FILE) else []
existing_keys = {(t["subject"], t["relation"], t["object"]) for t in triplets_all if isinstance(t, dict)}

start = time.time()
for i in tqdm(range(0, len(chunks), CHUNK_GROUP_SIZE), desc="🔍 Extracting", unit="group"):
    group = chunks[i:i + CHUNK_GROUP_SIZE]
    group_ids = [c["chunk_id"] for c in group]

    if all(gid in processed_ids for gid in group_ids):
        continue

    meta = group[0]
    context_title = meta.get("title", "")
    group_text = "\n".join(f"{context_title}\n{chunk['text']}" for chunk in group)

    # === Coreference Resolution ===
    resolved_text = resolve_coreferences(group_text)

    # === Rule-based Extraction ===
    rule_based = spacy_extract_triplets(resolved_text)
    rule_triplets = [
        generate_labeled_triplet_with_metadata(subj, pred, obj, meta)
        for subj, pred, obj in rule_based
    ]
    for t in rule_triplets:
        t["origin"] = "spacy"

    # === LLM Extraction with Filtering ===
    llm_raw = refine_with_llm(resolved_text, meta)
    llm_triplets = [
        generate_labeled_triplet_with_metadata(subj, pred, obj, meta)
        for subj, pred, obj in parse_triplets(llm_raw)
    ]
    for t in llm_triplets:
        t["origin"] = "llm"
        t["confidence"] = score_triplet(t["subject"], t["relation"], t["object"])
    llm_triplets = [t for t in llm_triplets if t["confidence"] >= 0.6]

    # === NER Extraction ===
    ner_triplets = []
    for e in enrich_with_ner(resolved_text):
        if not is_valid_ner_entity(e):
            continue
        t = generate_labeled_triplet_with_metadata(e, "ist erwähnt in", context_title or "Studientext", meta)
        t["origin"] = "ner"
        t["confidence"] = 0.7
        ner_triplets.append(t)

    # === Combine and Deduplicate ===
    all_triplets = rule_triplets + llm_triplets + ner_triplets
    unique_new = []
    for t in all_triplets:
        key = (t["subject"], t["relation"], t["object"])
        if key not in existing_keys:
            existing_keys.add(key)
            unique_new.append(t)

    triplets_all.extend(unique_new)
    processed_ids.update(group_ids)

    save_json(triplets_all, OUTPUT_FILE)
    save_json(list(processed_ids), PROGRESS_FILE)

# === Optional Filtering Step ===
triplets_filtered = [t for t in triplets_all if t["confidence"] >= 0.6 and t["origin"] != "ner"]
save_json(triplets_filtered, FILTERED_OUTPUT_FILE)

end = time.time()
print(f"\n✅ Done. {len(triplets_all)} triplets saved in {end-start:.2f}s. Filtered: {len(triplets_filtered)}")
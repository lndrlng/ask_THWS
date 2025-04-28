import torch
import pandas as pd
import requests
import time
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

# --- Config ---
CSV_INPUT     = "/Users/lelange/Uni/Projektarbeit/rag/testing/fragenkatalog_2104.csv"
CSV_OUTPUT    = "/Users/lelange/Uni/Projektarbeit/rag/testing/test_results.csv"
COLLECTION    = "thws_data_raw_chunks"
QDRANT_URL    = "http://localhost:6333"
EMBED_MODEL   = "BAAI/bge-m3"
MODELS = {
    "gemma:7b":       "answer_gemma7b",
    "orca-mini:7b":   "answer_orca-mini7b",
    "mistral:latest": "answer_mistral_latest",
    "phi4:latest":    "answer_phi4_latest",
    "qwen2.5:14b":    "answer_qwen2_5_14b",
    "orca-mini:13b":  "answer_orca-mini_13b",
    "gemma3:27b":     "answer_gemma3_27b",
    "deepseek-r1:32b":"answer_deepseek_r1_32b",
    "qwq:latest":     "answer_qwq_latest",
}
TOP_K         = 3
NUM_QUESTIONS = 20

# --- Device für Embeddings ---
if torch.cuda.is_available():
    device = "cuda"
elif torch.backends.mps.is_available() and torch.backends.mps.is_built():
    device = "mps"
else:
    device = "cpu"
print(f"🔥 Using device: {device}")

# --- Init Embedder & Qdrant-Client ---
embedder = SentenceTransformer(EMBED_MODEL, device=device)
client   = QdrantClient(url=QDRANT_URL)

# --- Lade Fragenkatalog (oberste 5 Zeilen) ---
df = pd.read_csv(CSV_INPUT)
# Filter questions starting from ID = 7
df_filtered = df[df["Id"] >= 7]
df_test = df_filtered.head(NUM_QUESTIONS).reset_index(drop=True)

results = []

for _, row in df_test.iterrows():
    question      = row["Question"]
    correct_ans   = row.get("Answer", "")
    print(f"\n--- Verarbeite Frage ID {row['Id']}")
    
    # 1) Embed Query
    q_vec = embedder.encode(question, device=device)
    # 2) Suche in Qdrant
    hits = client.search(
        collection_name=COLLECTION,
        query_vector=q_vec.tolist(),
        limit=TOP_K,
        with_payload=True,
    )
    
    # Dedupliziere nach Quelle
    unique = {}
    for hit in hits:
        src = hit.payload["source"]
        if src not in unique:
            unique[src] = hit
    context = "\n\n".join(h.payload["text"] for h in unique.values())
    row_source = row.get("URL / Dokument", "")
    
    # Bereite Ergebnis-Dict vor
    record = {
        "question": question,
        "correct_answer": correct_ans,
        "source": row_source,
    }

    # 3) Für jedes Modell einmal antworten
    for model_name, col_name in MODELS.items():
        print(f"Rufe Modell {model_name} auf...")
        prompt = f"""
Du bist ein hilfreicher Assistent der Hochschule THWS.
Beantworte die folgende Frage basierend auf dem gegebenen Kontext.
Antworte ausschließlich auf Deutsch und fasse dich klar und präzise.
Wenn du die Frage nicht beantworten kannst, antworte bitte mit "Diese Frage kann ich leider nicht beantworten."
Wenn du die richtige Antwort kennst, gib diese klar und präzise wieder.

Kontext:
{context}

Frage:
{question}

Antwort:
"""
        start_time = time.time()
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model_name, "prompt": prompt, "stream": False},
        )
        answer = resp.json().get("response", "").strip()
        duration = time.time() - start_time
        record[f"{col_name}_time"] = duration
        record[col_name] = answer
        print(f"[{model_name}] Dauer: {duration:.2f} Sekunden")

    results.append(record)

# 4) Schreibe Ergebnis-CSV
print("Schreibe Ergebnisse in:", CSV_OUTPUT)
pd.DataFrame(results).to_csv(CSV_OUTPUT, index=False, encoding="utf-8-sig")
print(f"✅ Fertig! Ergebnisse in »{CSV_OUTPUT}«.")
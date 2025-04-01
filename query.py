import sys
import torch
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
import requests

# --- Config ---
COLLECTION_NAME = "thws_data_chunks"
QDRANT_URL = "http://localhost:6333"
EMBED_MODEL_NAME = "BAAI/bge-m3"
OLLAMA_MODEL = "mistral"
TOP_K = 5

# --- Get User Query ---
if len(sys.argv) < 2:
    print(f"Usage: python {sys.argv[0]} \"your question here\"")
    sys.exit(1)

query = sys.argv[1]

# --- Load Embedding Model with CUDA ---
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"🔥 Using device: {device}")
embedder = SentenceTransformer(EMBED_MODEL_NAME, device=device)

# --- Embed Query ---
query_vec = embedder.encode(query, device=device)

# --- Search Qdrant ---
client = QdrantClient(url=QDRANT_URL)
search_results = client.search(
    collection_name=COLLECTION_NAME,
    query_vector=query_vec.tolist(),
    limit=TOP_K,
    with_payload=True
)

# --- Prepare Context ---
context = "\n\n".join([res.payload["text"] for res in search_results])

# --- Build Prompt ---
prompt = f"""
Du bist ein hilfreicher Assistent der Hochschule THWS.
Beantworte die folgende Frage basierend auf dem gegebenen Kontext.
Wenn du es nicht weißt, sag "Ich weiß es leider nicht."

Kontext:
{context}

Frage:
{query}

Antwort:
"""

# --- Call Ollama ---
response = requests.post(
    "http://localhost:11434/api/generate",
    json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
)

answer = response.json().get("response")
print("\n🤖 Answer:\n", answer.strip())

# --- Optional: Show sources ---
print("\n🔗 Sources:")
for res in search_results:
    print("-", res.payload["source"])

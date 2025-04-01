import sys
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
import requests

# --- Config ---
COLLECTION_NAME = "thws_data_chunks"
QDRANT_URL = "http://localhost:6333"
EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
OLLAMA_MODEL = "mistral"  # or "llama2" etc.
TOP_K = 5

# --- Get User Query ---
if len(sys.argv) < 2:
    print(f"Usage: python {sys.argv[0]} \"your question here\"")
    sys.exit(1)

query = sys.argv[1]

# --- Load Embedding Model ---
embedder = SentenceTransformer(EMBED_MODEL_NAME)

# --- Embed Query ---
query_vec = embedder.encode(query)

# --- Search Qdrant ---
client = QdrantClient(url=QDRANT_URL)
search_results = client.query_points(
    collection_name=COLLECTION_NAME,
    query_vector=query_vec.tolist(),
    limit=TOP_K,
    with_payload=True
)

# --- Prepare Context ---
context = "\n\n".join([res.payload["text"] for res in search_results])

# --- Build Prompt ---
prompt = f"""
You are an assistant answering questions about THWS.
Use the following context to answer the question.
If you don't know, say "I don't know".

Context:
{context}

Question:
{query}

Answer:
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

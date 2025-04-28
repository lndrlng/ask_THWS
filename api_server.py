import time
import torch
import requests
import warnings
import subprocess
import atexit
import os
import signal
from fastapi import FastAPI
from pydantic import BaseModel
from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
import uvicorn

# --- Config ---
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "kg123lol!1"
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "thws_data2_chunks"
EMBED_MODEL_NAME = "BAAI/bge-m3"
OLLAMA_MODEL = "mixtral"
TOP_K = 5

warnings.filterwarnings("ignore", category=DeprecationWarning)

# --- Device Setup ---
if torch.cuda.is_available():
    device = "cuda"
elif torch.backends.mps.is_available() and torch.backends.mps.is_built():
    device = "mps"
else:
    device = "cpu"
print(f"🔥 Using device: {device}")

embedder = SentenceTransformer(EMBED_MODEL_NAME, device=device)

# --- Clients ---
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
qdrant_client = QdrantClient(url=QDRANT_URL)

# --- Ollama server startup ---
ollama_process = subprocess.Popen(
    ["ollama", "serve"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL
)

def shutdown_ollama():
    print("🛑 Stopping Ollama server...")
    if os.name == "nt":
        ollama_process.terminate()
    else:
        os.killpg(os.getpgid(ollama_process.pid), signal.SIGTERM)

atexit.register(shutdown_ollama)

# --- FastAPI app ---
app = FastAPI()

class Question(BaseModel):
    query: str

# --- Retrieval functions ---
def search_graph_neo4j(query_text, top_k=TOP_K):
    with driver.session() as session:
        result = session.run("""
            MATCH (n)
            WHERE any(prop IN keys(n) WHERE toLower(n[prop]) CONTAINS toLower($query))
            RETURN n.name AS name, labels(n) AS labels
            LIMIT $top_k
        """, query=query_text, top_k=top_k)

        chunks = []
        for record in result:
            chunks.append(f"{', '.join(record['labels'])}: {record['name']}")
    return chunks

def search_qdrant(query_text, top_k=TOP_K):
    query_vec = embedder.encode(query_text, device=device)
    search_results = qdrant_client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vec.tolist(),
        limit=top_k,
        with_payload=True,
    )
    chunks = []
    for res in search_results:
        chunks.append(res.payload.get("text", ""))
    return chunks

def build_prompt(graph_chunks, vdb_chunks, query_text):
    graph_context = "\n".join(graph_chunks) if graph_chunks else "Keine Graph-Informationen gefunden."
    vdb_context = "\n".join(vdb_chunks) if vdb_chunks else "Keine Text-Informationen gefunden."

    prompt = f"""
Du bist ein hilfreicher Assistent der Hochschule THWS.
Nutze die folgenden Informationen aus dem Wissensgraphen und aus Textdokumenten, um die Frage zu beantworten.
Wenn du keine ausreichenden Informationen hast, sage "Ich weiß es leider nicht."

Graph-Kontext:
{graph_context}

Text-Kontext:
{vdb_context}

Frage:
{query_text}

Antwort:
"""
    return prompt

def query_ollama(prompt):
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
    )
    return response.json().get("response", "").strip()

# --- API Endpoints ---
@app.post("/ask")
def ask(data: Question):
    start = time.time()

    graph_chunks = search_graph_neo4j(data.query)
    vdb_chunks = search_qdrant(data.query)

    prompt = build_prompt(graph_chunks, vdb_chunks, data.query)
    answer = query_ollama(prompt)

    duration = round(time.time() - start, 2)
    return {
        "question": data.query,
        "answer": answer,
        "graph_hits": graph_chunks,
        "vdb_hits": vdb_chunks,
        "duration_seconds": duration,
    }

@app.get("/metadata")
def metadata():
    commit = subprocess.getoutput("git rev-parse HEAD")
    return {
        "embedding_model": EMBED_MODEL_NAME,
        "llm_model": OLLAMA_MODEL,
        "git_commit": commit,
        "device": device
    }

# --- Run if main ---
if __name__ == "__main__":
    uvicorn.run("graph_rag_combined:app", host="0.0.0.0", port=8000, reload=False)

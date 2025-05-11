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
from numpy import dot
from numpy.linalg import norm

# --- Config ---
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "kg123lol!1"
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "thws_data2_chunks"
EMBED_MODEL_NAME = "BAAI/bge-m3"
OLLAMA_MODEL = "mistral"  # ← ersetzt 'mixtral' durch das ressourcenschonendere Modell
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
    ["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
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


# --- Graph Retrieval: Full-text index ---
def search_graph_fulltext(query_text, top_k=TOP_K):
    with driver.session() as session:
        cypher = """
            CALL db.index.fulltext.queryNodes('entityIndex', $search_text)
            YIELD node, score
            RETURN node.name AS name, labels(node) AS labels, score
            ORDER BY score DESC
            LIMIT $limit
        """
        result = session.run(cypher, search_text=query_text, limit=top_k)
        return [
            f"{', '.join(record['labels'])}: {record['name']} (Score: {record['score']:.2f})"
            for record in result
        ]

# --- Graph Retrieval: Node Embeddings ---
def search_graph_by_embedding(query_text, top_k=TOP_K):
    query_embedding = embedder.encode(query_text, device=device).tolist()
    labels = ["PER", "ORG", "PROGRAM"]
    hits = []

    with driver.session() as session:
        for label in labels:
            index_name = f"entityEmbeddingIndex_{label}"
            result = session.run("""
                CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
                YIELD node, score
                RETURN node.name AS name, labels(node) AS labels, score
            """, index_name=index_name, embedding=query_embedding, top_k=top_k)
            hits.extend(result)

    seen = set()
    unique_hits = []
    for record in hits:
        key = (record['name'], tuple(record['labels']))
        if key not in seen:
            seen.add(key)
            unique_hits.append(
                f"{', '.join(record['labels'])}: {record['name']} (Score: {record['score']:.2f})"
            )

    return unique_hits

# --- Graph Retrieval: Relationship Embeddings ---
def search_triplet_embeddings(query_text, top_k=TOP_K):
    query_vec = embedder.encode(query_text, device=device).tolist()

    with driver.session() as session:
        result = session.run("""
            MATCH (a)-[r]->(b)
            WHERE r.triplet_embedding IS NOT NULL
            RETURN r, a.name AS subj, type(r) AS rel, b.name AS obj, r.triplet_embedding AS emb
        """)

        scored = []
        for record in result:
            emb = record["emb"]
            if not emb:
                continue
            sim = dot(query_vec, emb) / (norm(query_vec) * norm(emb) + 1e-5)
            scored.append((
                sim,
                f"{record['subj']} -[{record['rel']}]-> {record['obj']} (Score: {sim:.2f})"
            ))

        top_matches = sorted(scored, key=lambda x: x[0], reverse=True)[:top_k]
        return [x[1] for x in top_matches]

# --- Vector DB Retrieval (Qdrant) ---
def search_qdrant(query_text, top_k=TOP_K):
    query_vec = embedder.encode(query_text, device=device)
    search_results = qdrant_client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vec.tolist(),
        limit=top_k,
        with_payload=True,
    )
    return [res.payload.get("text", "") for res in search_results]


# --- Prompt construction ---
def build_prompt(graph_chunks, vdb_chunks, query_text):
    graph_context = (
        "\n".join(graph_chunks)
        if graph_chunks
        else "Keine Graph-Informationen gefunden."
    )
    vdb_context = (
        "\n".join(vdb_chunks) if vdb_chunks else "Keine Text-Informationen gefunden."
    )

    print(graph_chunks)

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


# --- Ollama call ---
def query_ollama(prompt):
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
    )
    data = response.json()
    print("🧠 Ollama raw response:", data)  # <- Zum Debuggen
    return data.get("response", "").strip() or "Ich weiß es leider nicht."

# --- API Endpoints ---
@app.post("/ask")
def ask(data: Question):
    start = time.time()

    graph_chunks = list(set(
        search_graph_fulltext(data.query)
        + search_graph_by_embedding(data.query)
        + search_triplet_embeddings(data.query)
    ))

    vdb_chunks = search_qdrant(data.query)
    prompt = build_prompt(graph_chunks, vdb_chunks, data.query)
    answer = query_ollama(prompt)

    duration = round(time.time() - start, 2)
    return {
        "question": data.query,
        "answer": answer,
        "graph_hits": graph_chunks,
        "vdb_hits": vdb_chunks,
        "sources": graph_chunks + vdb_chunks,  # ✅ Always include sources
        "duration_seconds": duration,
    }


@app.get("/metadata")
def metadata():
    commit = subprocess.getoutput("git rev-parse HEAD")
    return {
        "embedding_model": EMBED_MODEL_NAME,
        "llm_model": OLLAMA_MODEL,
        "git_commit": commit,
        "device": device,
        "triplet_embeddings": True
    }


# --- Run ---
if __name__ == "__main__":
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=False)
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=False)

import json
import sys
import os
import uuid
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

# --- CLI Input ---
if len(sys.argv) < 2:
    print(f"Usage: python {sys.argv[0]} <chunks_file.json>")
    sys.exit(1)

CHUNKS_PATH = sys.argv[1]
COLLECTION_NAME = os.path.splitext(os.path.basename(CHUNKS_PATH))[0]  # e.g. "thws_data_chunks"
EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
QDRANT_URL = "http://localhost:6333"
EMBED_DIM = 384  # depends on model

# --- Load Chunks ---
with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
    chunks = json.load(f)

# --- Load Embedding Model ---
model = SentenceTransformer(EMBED_MODEL_NAME)

# --- Init Qdrant Client ---
qdrant = QdrantClient(url=QDRANT_URL)

# --- Create Collection ---
qdrant.recreate_collection(
    collection_name=COLLECTION_NAME,
    vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE)
)

# --- Prepare and Upload Vectors ---
points = []
texts = [chunk["text"] for chunk in chunks]
embeddings = model.encode(texts, show_progress_bar=True)

for i, chunk in enumerate(chunks):
    vector = embeddings[i]
    payload = {
        "text": chunk["text"],
        "source": chunk["source"],
        "chunk_id": chunk["chunk_id"],
        "type": chunk["type"],
        "language": chunk["language"]
    }
    points.append(
        PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload=payload
        )
    )

# --- Upload ---
BATCH_SIZE = 64  # safe size

for i in tqdm(range(0, len(points), BATCH_SIZE), desc="Uploading to Qdrant"):
    batch = points[i:i + BATCH_SIZE]
    qdrant.upsert(
        collection_name=COLLECTION_NAME,
        points=batch
    )

print(f"✅ Uploaded {len(points)} chunks to Qdrant collection '{COLLECTION_NAME}'")

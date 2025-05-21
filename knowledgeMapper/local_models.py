# local_models.py  – updated 21 May 2025
from langchain.embeddings import HuggingFaceEmbeddings
import requests

# ── pick the embedding model you want ────────────────────────────────
#EMBEDDING_MODEL_NAME = "nvidia/NV-Embed-v2"   # best quality, 4096-d
# Alternatives:
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"        # multilingual, 1024-d
# EMBEDDING_MODEL_NAME = "intfloat/e5-base-v2"  # fast & light, 768-d

# ── LLM for answer generation (unchanged) ───────────────────────────
OLLAMA_MODEL_NAME = "mistral"
OLLAMA_HOST       = "http://localhost:11434"

# ─────────────────────────────────────────────────────────────────────
class HFEmbedFunc:
    """Callable wrapper that satisfies LightRAG’s contract."""
    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME):
        self.model = HuggingFaceEmbeddings(model_name=model_name)

        # LightRAG & nano-vectordb need this attribute ⬇
        self.embedding_dim = self.model.client.get_sentence_embedding_dimension()

    def __call__(self, texts: list[str]) -> list[list[float]]:
        return self.model.embed_documents(texts)

class OllamaLLM:
    def __call__(self, prompt: str) -> str:
        response = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": OLLAMA_MODEL_NAME, "prompt": prompt, "stream": False},
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["response"]

from langchain.embeddings import HuggingFaceEmbeddings
import requests

# === Configuration Section ===
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
OLLAMA_MODEL_NAME = "mistral"  # Change to "llama2", "gemma", etc.
OLLAMA_HOST = "http://localhost:11434"


# =============================

class HFEmbedFunc:
    def __init__(self):
        self.model = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)

    def __call__(self, texts):
        return self.model.embed_documents(texts)


class OllamaLLM:
    def __call__(self, prompt: str) -> str:
        response = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": OLLAMA_MODEL_NAME, "prompt": prompt, "stream": False},
            timeout=60
        )
        response.raise_for_status()
        return response.json()["response"]

from __future__ import annotations

"""
local_models.py – last updated 22 May 2025

• Async **BGE-M3** embedder with `embedding_dim = 1024`
• Async Ollama LLM wrapper that swallows LightRAG-HKU kwargs
• Legacy alias `HFEmbedFunc` so older imports keep working
"""

import asyncio
import requests
from langchain.embeddings import HuggingFaceEmbeddings

# ── configuration ───────────────────────────────────────────────────────
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
OLLAMA_MODEL_NAME = "mistral"
OLLAMA_HOST = "http://localhost:11434"

# ── blocking HuggingFace embedder ───────────────────────────────────────
_hf = HuggingFaceEmbeddings(
    model_name=EMBEDDING_MODEL_NAME,
    encode_kwargs={"normalize_embeddings": True},
)
EMBED_DIM = _hf.client.get_sentence_embedding_dimension()  # 1024


# ── async wrapper expected by LightRAG-HKU ──────────────────────────────
class AsyncEmbedder:
    embedding_dim: int = EMBED_DIM  # <- LightRAG reads this

    async def __call__(self, texts: list[str]) -> list[list[float]]:
        # run the blocking encode in a worker thread
        return await asyncio.to_thread(_hf.embed_documents, texts)

# Create an instance of the embedder class
_async_embedder_instance = AsyncEmbedder()

# Define a wrapper function that will be the actual embedding_func
async def embedding_wrapper_func(texts: list[str]) -> list[list[float]]:
    """
    Wrapper function for the async embedder's __call__ method.
    This function will have embedding_dim attached to it.
    """
    return await _async_embedder_instance(texts)

# Attach the embedding_dim to the wrapper function itself
embedding_wrapper_func.embedding_dim = _async_embedder_instance.embedding_dim

# Export the wrapper function as embedding_func
embedding_func = embedding_wrapper_func  # ← This is now a function with an embedding_dim attribute


# ── Ollama completion (async) ───────────────────────────────────────────
class OllamaLLM:
    async def __call__(  # signature matches LightRAG-HKU
            self,
            prompt: str,
            system_prompt: str | None = None,
            history_messages: list[dict] | None = None,
            **kwargs,
    ) -> str:
        for k in ("hashing_kv", "max_tokens", "response_format"):
            kwargs.pop(k, None)  # discard unused control kwargs

        parts = []
        if history_messages:
            parts.append("\n".join(m.get("content", "") for m in history_messages))
        if system_prompt:
            parts.append(system_prompt)
        parts.append(prompt)
        full_prompt = "\n".join(parts)

        def _call() -> str:
            r = requests.post(
                f"{OLLAMA_HOST}/api/generate",
                json={"model": OLLAMA_MODEL_NAME, "prompt": full_prompt, "stream": False},
                timeout=180,
            )
            r.raise_for_status()
            return r.json()["response"]

        return await asyncio.to_thread(_call)


# ── legacy shim so old code keeps working ───────────────────────────────
class HFEmbedFunc:  # noqa: N801
    """Deprecated alias – returns the singleton embedder."""

    def __new__(cls, *_, **__):  # noqa: D401
        # This will now return the embedding_wrapper_func
        return embedding_func


__all__ = ["embedding_func", "OllamaLLM", "HFEmbedFunc"]
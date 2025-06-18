from __future__ import annotations

"""
local_models.py – updated 26 May 2025 (OOM-safe version)

• BGE‑M3 embedder runs async on GPU with semaphore to prevent OOM
• Qwen‑3 14B‑Q4_K_M LLM runs via Ollama API with 16 k context
• Memory-managed: low batch size, no_grad, empty_cache per batch
"""

import asyncio
import requests
import torch
from langchain.embeddings import HuggingFaceEmbeddings

# ── configuration ───────────────────────────────────────────────────────
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
EMBEDDING_DEVICE = "cpu"  # GPU target
BATCH_SIZE = 16  # reduced for memory stability
_EMBED_SEMAPHORE = asyncio.Semaphore(2)  # throttle concurrency

# LLM runtime settings ---------------------------------------------------
OLLAMA_MODEL_NAME = "mistral"
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_NUM_CTX = 16384       # 16k tokens (≈4 GB KV)
OLLAMA_NUM_PREDICT = 4096    # up to 4k tokens of completion

# ── HuggingFace embedder (on GPU) ───────────────────────────────────────
_hf = HuggingFaceEmbeddings(
    model_name=EMBEDDING_MODEL_NAME,
    encode_kwargs={"normalize_embeddings": True},
    model_kwargs={"device": EMBEDDING_DEVICE},
)
EMBED_DIM = _hf.client.get_sentence_embedding_dimension()  # 1024 for BGE-M3


# ── async-safe embedding wrapper ────────────────────────────────────────
class AsyncEmbedder:
    """Callable embedder with memory-managed async behavior."""

    embedding_dim: int = EMBED_DIM

    async def __call__(self, texts: list[str]) -> list[list[float]]:
        """Async entry point with semaphore and background execution."""
        async with _EMBED_SEMAPHORE:
            return await asyncio.to_thread(self._embed_chunked, texts)

    def _embed_chunked(self, texts: list[str]) -> list[list[float]]:
        """Internal CPU-threaded embedding loop with memory control."""
        vecs: list[list[float]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            with torch.no_grad():
                vecs.extend(_hf.embed_documents(batch))
            torch.cuda.empty_cache()  # help reduce fragmentation
        return vecs


# ── embedding API expected by LightRAG ──────────────────────────────────
_async_embedder_instance = AsyncEmbedder()


async def embedding_wrapper_func(texts: list[str]) -> list[list[float]]:
    return await _async_embedder_instance(texts)


embedding_wrapper_func.embedding_dim = _async_embedder_instance.embedding_dim  # type: ignore[attr-defined]
embedding_func = embedding_wrapper_func


# ── Ollama async wrapper (unchanged) ────────────────────────────────────
class OllamaLLM:
    """Thin async wrapper around Ollama’s /api/generate endpoint."""

    async def __call__(
            self,
            prompt: str,
            system_prompt: str | None = None,
            history_messages: list[dict] | None = None,
            **kwargs,
    ) -> str:
        for k in ("hashing_kv", "max_tokens", "response_format"):
            kwargs.pop(k, None)

        parts: list[str] = []
        if history_messages:
            parts.append("\n".join(m.get("content", "") for m in history_messages))
        if system_prompt:
            parts.append(system_prompt)
        parts.append(prompt)
        full_prompt = "\n".join(parts)

        def _call() -> str:
            r = requests.post(
                f"{OLLAMA_HOST}/api/generate",
                json={
                    "model": OLLAMA_MODEL_NAME,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {
                        "num_ctx": OLLAMA_NUM_CTX,
                        "num_predict": OLLAMA_NUM_PREDICT,
                    },
                },
                timeout=10_000,
            )
            r.raise_for_status()
            return r.json()["response"]

        return await asyncio.to_thread(_call)


# ── legacy alias (keeps older imports working) ──────────────────────────
class HFEmbedFunc:  # noqa: N801
    def __new__(cls, *_, **__):
        return embedding_func


__all__ = [
    "embedding_func",
    "OllamaLLM",
    "HFEmbedFunc",
    "EMBEDDING_MODEL_NAME",
    "OLLAMA_MODEL_NAME"

]

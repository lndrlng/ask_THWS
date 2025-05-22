from __future__ import annotations

"""
local_models.py – updated fix 22 May 2025

• Async **BGE‑M3** embedder that really runs on the GPU (device="cuda")
• Manual batching (128 docs) to stay compatible with older LangChain versions
• Ollama wrapper with 8 k context + 2 k generation
• Legacy alias `HFEmbedFunc` so older imports keep working
"""

import asyncio
import requests
from langchain.embeddings import HuggingFaceEmbeddings

# ── configuration ───────────────────────────────────────────────────────
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
EMBEDDING_DEVICE = "cuda"  # run on your Tesla V100
BATCH_SIZE = 128  # manual batch size (safe for LC <0.2.0)

OLLAMA_MODEL_NAME = "qwen3:14b-q4_K_M"
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_NUM_CTX = 32768     # ≈8 k tokens of prompt/context
OLLAMA_NUM_PREDICT = 8192     # ≈2 k tokens of completion

# ── blocking HuggingFace embedder (initialised on CUDA) ────────────────
_hf = HuggingFaceEmbeddings(
    model_name=EMBEDDING_MODEL_NAME,
    encode_kwargs={"normalize_embeddings": True},
    model_kwargs={"device": EMBEDDING_DEVICE},
)
EMBED_DIM = _hf.client.get_sentence_embedding_dimension()  # 1024 for BGE‑M3


# ── async wrapper expected by LightRAG‑HKU ──────────────────────────────
class AsyncEmbedder:
    """Callable object that exposes an `embedding_dim` attribute."""

    embedding_dim: int = EMBED_DIM

    async def __call__(self, texts: list[str]) -> list[list[float]]:  # noqa: D401
        """Embed `texts` in chunks so we stay version‑compatible."""

        def _embed_chunked() -> list[list[float]]:
            vecs: list[list[float]] = []
            for i in range(0, len(texts), BATCH_SIZE):
                vecs.extend(_hf.embed_documents(texts[i: i + BATCH_SIZE]))
            return vecs

        return await asyncio.to_thread(_embed_chunked)


# Shared singleton keeps the model in memory once
_async_embedder_instance = AsyncEmbedder()


async def embedding_wrapper_func(texts: list[str]) -> list[list[float]]:
    """Public embedding entry point (function w/ attribute)."""
    return await _async_embedder_instance(texts)


# Expose the attribute LightRAG inspects
embedding_wrapper_func.embedding_dim = _async_embedder_instance.embedding_dim  # type: ignore[attr-defined]

# Preferred import target
embedding_func = embedding_wrapper_func


# ── Ollama completion (async) ───────────────────────────────────────────
class OllamaLLM:
    """Thin async wrapper around Ollama’s /api/generate endpoint."""

    async def __call__(
            self,
            prompt: str,
            system_prompt: str | None = None,
            history_messages: list[dict] | None = None,
            **kwargs,
    ) -> str:
        # Drop LightRAG‑specific kwargs that Ollama ignores
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


# ── legacy shim so old code keeps working ───────────────────────────────
class HFEmbedFunc:  # noqa: N801
    """Deprecated alias – returns the singleton embedder function."""

    def __new__(cls, *_, **__):  # noqa: D401
        return embedding_func


__all__ = [
    "embedding_func",
    "OllamaLLM",
    "HFEmbedFunc",
]

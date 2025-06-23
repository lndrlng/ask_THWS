from pathlib import Path
from typing import Dict

from lightrag_hku import LightRAG

from local_models import embedding_func, OllamaLLM

BASE_STORAGE_DIR = Path("../rag_storage_hku")

_rag_instance: LightRAG | None = None


def get_rag_instance() -> LightRAG:
    """
    Factory to load and cache the single, unified RAG instance.
    """
    global _rag_instance
    if _rag_instance:
        return _rag_instance

    if not BASE_STORAGE_DIR.exists():
        raise ValueError(
            f"Database not found at '{BASE_STORAGE_DIR}'. Did you run the build script `knowledgeMapper/build_dbs.py`?"
        )

    print(f"[*] Loading unified RAG instance from: {BASE_STORAGE_DIR}")

    rag = LightRAG(
        working_dir=str(BASE_STORAGE_DIR),
        embedding_func=embedding_func,
        llm_model_func=OllamaLLM(),
    )
    _rag_instance = rag
    print("[*] RAG instance loaded successfully.")
    return rag

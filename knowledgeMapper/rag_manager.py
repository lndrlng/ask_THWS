from pathlib import Path
from typing import Dict

from lightrag import LightRAG

import config 
from utils.local_models import embedding_func, OllamaLLM


_rag_instance: LightRAG | None = None


def get_rag_instance() -> LightRAG:
    """
    Factory to load and cache the single, unified RAG instance from the
    directory specified in config.py.
    """
    global _rag_instance
    if _rag_instance:
        return _rag_instance

    storage_path = config.BASE_STORAGE_DIR

    if not storage_path.exists():
        raise ValueError(
            f"Database not found at '{storage_path}'. Did you run the build script `build_dbs.py`?"
        )

    print(f"[*] Loading unified RAG instance from: {storage_path}")

    rag = LightRAG(
        working_dir=str(storage_path),
        embedding_func=embedding_func,
        llm_model_func=OllamaLLM(),
    )
    _rag_instance = rag
    print("[*] RAG instance loaded successfully.")
    return rag
import asyncio
from pathlib import Path
from lightrag import LightRAG
from lightrag.kg.shared_storage import initialize_pipeline_status
from local_models import embedding_func, OllamaLLM
from file_loader import load_documents

DOC_DIR = Path("../data/ChatbotStuff")
WORK_DIR = "../rag_storage"


async def main() -> None:
    print("[*] Loading documents...")
    docs = load_documents(DOC_DIR)
    print(f"[*] Loaded {len(docs)} documents (which may become more chunks)")

    rag = LightRAG(
        working_dir=WORK_DIR,
        embedding_func=embedding_func,
        llm_model_func=OllamaLLM(),
    )
    print("[*] Initializing storages...")
    await rag.initialize_storages()
    await initialize_pipeline_status()
    print("[*] Storages initialized.")

    print("[*] Enqueuing documents...")
    await rag.apipeline_enqueue_documents(
        [d.page_content for d in docs],
        file_paths=[d.metadata.get("source_file") for d in docs], # Changed to .get() for safety
    )
    print("[*] Documents enqueued.")
    print("[*] Processing enqueued documents...")
    await rag.apipeline_process_enqueue_documents()
    print("✅ Knowledge graph + index build process initiated successfully for build_kg.py.")


if __name__ == "__main__": # Added main guard
    asyncio.run(main())
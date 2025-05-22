import asyncio
from pathlib import Path
from lightrag import LightRAG
from lightrag.kg.shared_storage import initialize_pipeline_status
from local_models import embedding_func, OllamaLLM
from file_loader import load_documents

DOC_DIR = Path("../data/ChatbotStuff")
WORK_DIR = "../rag_storage"


async def main() -> None:
    print("[*] Loading documents …")
    docs = load_documents(DOC_DIR)
    texts = [d.page_content for d in docs]
    file_paths = [d.metadata.get("source_file") for d in docs]
    print(f"[*] Loaded {len(texts)} chunks")

    rag = LightRAG(
        working_dir=WORK_DIR,
        embedding_func=embedding_func,  # async, embedding_dim = 1024
        llm_model_func=OllamaLLM(),  # async Ollama completion
    )

    await rag.initialize_storages()
    await initialize_pipeline_status()

    await rag.apipeline_enqueue_documents(texts, file_paths=file_paths)
    await rag.apipeline_process_enqueue_documents()

    print("✅ Knowledge graph + index built successfully")


if __name__ == "__main__":
    asyncio.run(main())
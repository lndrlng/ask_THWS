# build_kg.py

import asyncio
from lightrag import LightRAG
from local_models import HFEmbedFunc, OllamaLLM
from file_loader import load_documents


async def main():
    print("📥 Loading documents from ./data...")
    documents = load_documents("./data/ChatbotStuff")
    print(f"🔎 {len(documents)} documents loaded.")

    print("⚙️ Initializing LightRAG with local LLM + Embeddings...")
    rag = LightRAG(
        working_dir="./rag_storage",
        embedding_func=HFEmbedFunc(),
        llm_model_func=OllamaLLM()
    )
    await rag.initialize_storages()

    print("🧠 Building Knowledge Graph from documents...")
    await rag.apipeline_enqueue_documents(documents)
    await rag.apipeline_process_enqueue_documents()

    print("✅ Knowledge graph + vector index saved to ./rag_storage")


asyncio.run(main())

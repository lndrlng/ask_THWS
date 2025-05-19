# File: preprocess_data.py

import asyncio
from lightrag import LightRAG
from local_models import HFEmbedFunc, OllamaLLM
from file_loader import load_documents


async def main():
    print("[*] Loading documents from multiple formats...")
    documents = load_documents("../data/ChatbotStuff")

    print(f"[*] Loaded and split into {len(documents)} chunks.")

    print("[*] Initializing LightRAG and building knowledge graph...")
    rag = LightRAG(
        working_dir="./rag_storage",
        embedding_func=HFEmbedFunc(),
        llm_model_func=OllamaLLM()
    )

    await rag.initialize_storages()
    await rag.apipeline_enqueue_documents(documents)
    await rag.apipeline_process_enqueue_documents()

    print("[✓] Knowledge graph and index saved successfully.")


if __name__ == "__main__":
    asyncio.run(main())

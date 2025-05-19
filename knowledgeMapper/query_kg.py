# query_kg.py

import asyncio
from lightrag import LightRAG, QueryParam
from local_models import HFEmbedFunc, OllamaLLM


async def main():
    print("📂 Loading LightRAG storage from ./rag_storage")
    rag = LightRAG(
        working_dir="./rag_storage",
        embedding_func=HFEmbedFunc(),
        llm_model_func=OllamaLLM()
    )
    await rag.initialize_storages()

    while True:
        question = input("❓ Ask a question (or type 'exit'): ").strip()
        if question.lower() in {"exit", "quit"}:
            break

        print("🤖 Thinking...")
        result = await rag.aquery(question, param=QueryParam(mode="hybrid"))
        print("💬 Answer:", result)


asyncio.run(main())

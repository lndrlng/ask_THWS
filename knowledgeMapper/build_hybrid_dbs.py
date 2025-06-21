
import asyncio
import os
from pathlib import Path
from collections import defaultdict
from typing import List, Dict

from langchain.docstore.document import Document
from lightrag import LightRAG

from lightrag.components.graph_store import GraphStore
from lightrag.components.vector_store import VectorStore
from lightrag.kg.shared_storage import initialize_pipeline_status

from local_models import embedding_func, OllamaLLM
from file_loader import load_documents
from utils.subdomain_utils import get_sanitized_subdomain

DOC_DIR = Path("../data/ChatbotStuff")
BASE_STORAGE_DIR = Path("../rag_storage")
# Define specific paths for the shared KG and the per-subdomain vector stores
KG_DIR = BASE_STORAGE_DIR / "global_kg"
VECTOR_STORES_DIR = BASE_STORAGE_DIR / "vector_stores"


async def main() -> None:
    """
    Builds a hybrid RAG storage: one vector store per subdomain and one shared KG.
    """
    print(f"[*] Loading all documents from: {DOC_DIR.resolve()}")
    docs = load_documents(DOC_DIR)
    print(f"[*] Loaded {len(docs)} total document chunks.")

    # 1. Group documents by their sanitized subdomain.
    print("[*] Grouping documents by subdomain...")
    docs_by_subdomain: Dict[str, List[Document]] = defaultdict(list)
    for doc in docs:
        # The URL is expected in the document's metadata from file_loader.py
        url = doc.metadata.get("url")
        subdomain_name = get_sanitized_subdomain(url)
        docs_by_subdomain[subdomain_name].append(doc)

    print(
        f"[*] Found {len(docs_by_subdomain)} subdomains to process: {list(docs_by_subdomain.keys())}"
    )

    # 2. Instantiate the SINGLE, SHARED Knowledge Graph Store.
    os.makedirs(KG_DIR, exist_ok=True)
    shared_graph_store = GraphStore(save_dir=str(KG_DIR))
    print(f"[*] Shared Knowledge Graph store will be saved to: {KG_DIR.resolve()}")

    # 3. Iterate over each subdomain to build its specific vector store.
    for subdomain, subdomain_docs in docs_by_subdomain.items():
        print(
            f"\n--- Processing Subdomain: {subdomain} ({len(subdomain_docs)} chunks) ---"
        )

        # Define a unique directory for this subdomain's vector store.
        subdomain_vector_dir = VECTOR_STORES_DIR / subdomain
        os.makedirs(subdomain_vector_dir, exist_ok=True)

        # Instantiate a SPECIFIC VectorStore for this subdomain.
        subdomain_vector_store = VectorStore(save_dir=str(subdomain_vector_dir))
        print(
            f"[*] VectorStore for '{subdomain}' will be saved to: {subdomain_vector_dir.resolve()}"
        )

        # 4. Instantiate LightRAG with the SHARED KG and the SPECIFIC VectorStore.
        rag = LightRAG(
            graph_store=shared_graph_store,
            vector_store=subdomain_vector_store,
            embedding_func=embedding_func,
            llm_model_func=OllamaLLM(),
        )

        # Initialize storages for this specific configuration.
        await rag.initialize_storages()
        await initialize_pipeline_status()

        print(f"[*] Enqueuing {len(subdomain_docs)} documents for '{subdomain}'...")
        texts = [d.page_content for d in subdomain_docs]
        file_paths = [d.metadata.get("source_file") for d in subdomain_docs]
        await rag.apipeline_enqueue_documents(texts, file_paths=file_paths)

        # Process the queue. This will populate this subdomain's vector store
        # and add to the shared knowledge graph.
        await rag.apipeline_process_enqueue_documents()
        print(f"✅ Hybrid build for '{subdomain}' complete.")

    print(
        "\n\n✅ All subdomain databases and the global knowledge graph have been built successfully."
    )


if __name__ == "__main__":
    asyncio.run(main())

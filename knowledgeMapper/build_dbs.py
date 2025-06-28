import os

os.environ["TOKENIZERS_PARALLELISM"] = "false"

import asyncio
import logging
import argparse
import json
from pathlib import Path
from collections import defaultdict
from typing import List, Dict

from rich.logging import RichHandler
from langchain.docstore.document import Document
from lightrag.kg.shared_storage import initialize_pipeline_status
from lightrag.lightrag import LightRAG

import config
from utils.chunker import create_structured_chunks
from utils.subdomain_utils import get_sanitized_subdomain
from utils.local_models import embedding_func, OllamaLLM
from utils.debug_utils import log_config_summary
from utils.mongo_loader import load_documents_from_mongo
from utils.progress_bar import get_kg_progress_bar, monitor_progress

logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)
log = logging.getLogger(__name__)


async def init_rag_instance(storage_dir: str) -> LightRAG:
    """Creates and initializes a LightRAG instance for building a Knowledge Graph."""
    rag = LightRAG(
        working_dir=storage_dir,
        embedding_func=embedding_func,
        llm_model_func=OllamaLLM(),
        entity_extract_max_gleaning=config.ENTITY_EXTRACT_MAX_GLEANING,
    )
    await rag.initialize_storages()
    await initialize_pipeline_status()
    return rag


async def build_knowledge_graph(docs_to_process: List[Document]):
    """Builds a single knowledge graph with the new, enhanced progress bar."""
    log.info(f"--- Building Knowledge Graph from {len(docs_to_process)} documents ---")
    rag = None
    try:
        storage_path = config.BASE_STORAGE_DIR.resolve()
        storage_path.mkdir(parents=True, exist_ok=True)
        rag = await init_rag_instance(storage_path.as_posix())

        log.info("Applying structured chunking...")
        structured_chunks = create_structured_chunks(docs_to_process)
        chunk_count = len(structured_chunks)
        log.info(f"Split documents into {chunk_count} structured chunks.")

        texts = [chunk.page_content for chunk in structured_chunks]
        paths = [chunk.metadata.get("url", "source_unknown") for chunk in structured_chunks]
        await rag.apipeline_enqueue_documents(texts, file_paths=paths)

        with get_kg_progress_bar() as progress:
            task_id = progress.add_task("main_build", total=chunk_count)
            status_file_path = Path(rag.working_dir) / "kv_store_doc_status.json"

            main_processing_task = asyncio.create_task(rag.apipeline_process_enqueue_documents())
            monitor_task = asyncio.create_task(
                monitor_progress(progress, task_id, status_file_path, main_processing_task)
            )
            
            await asyncio.gather(main_processing_task, monitor_task)
            progress.update(task_id, completed=chunk_count)

        log.info("[bold green]✅ Unified Knowledge Graph built successfully.[/bold green]")
        return True
    except Exception as e:
        log.exception(f"❌ FAILED to build knowledge graph: {e}")
        return False
    finally:
        if rag:
            await rag.finalize_storages()


async def main(args):
    """Main entrypoint: Loads documents, filters, and builds the KG."""
    log_config_summary()

    all_documents, load_stats = load_documents_from_mongo()
    if not all_documents:
        log.warning("No documents loaded from MongoDB. Aborting.")
        return

    docs_to_process = []
    if args.subdomain:
        log.info(f"Filtering for subdomains: {args.subdomain}")
        selected_subdomains = set(args.subdomain)
        for doc in all_documents:
            url = doc.metadata.get("url")
            subdomain = get_sanitized_subdomain(url)
            if subdomain in selected_subdomains:
                docs_to_process.append(doc)
        if not docs_to_process:
            log.error("None of the specified subdomains were found. Aborting.")
            return
    else:
        log.info("No subdomain filter provided. Using all loaded documents.")
        docs_to_process = all_documents

    success = await build_knowledge_graph(docs_to_process)

    if success:
        log.info("✅ Build process completed successfully.")
    else:
        log.warning("❌ Build process failed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build a RAG Knowledge Graph from MongoDB content."
    )
    parser.add_argument(
        "--subdomain",
        nargs="*",
        help="Build KG using only documents from one or more specific subdomains.",
    )
    args = parser.parse_args()
    asyncio.run(main(args))

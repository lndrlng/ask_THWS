import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"  # Avoids excessive parallelism warnings from tokenizer libs

import asyncio
import logging
import argparse
from collections import defaultdict
from typing import List, Dict

from rich.logging import RichHandler
from rich.progress import Progress

from langchain.docstore.document import Document
from lightrag.kg.shared_storage import initialize_pipeline_status
from lightrag.lightrag import LightRAG

import config
from utils.mongo_loader import load_documents_from_mongo
from utils.subdomain_utils import get_sanitized_subdomain
from utils.local_models import embedding_func, OllamaLLM

# Setup logging format and output
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)
log = logging.getLogger(__name__)


def flatten_documents(docs_by_subdomain: Dict[str, List[Document]]) -> tuple[list[str], list[str]]:
    """
    Flattens a nested dict of subdomain -> docs into two flat lists:
    - all document texts
    - all corresponding file paths (URLs).
    Useful when building a unified knowledge graph.
    """
    texts = [doc.page_content for docs in docs_by_subdomain.values() for doc in docs]
    paths = [doc.metadata.get("url", "source_unknown") for docs in docs_by_subdomain.values() for doc in docs]
    return texts, paths


async def init_rag_instance(
    storage_dir: str,
    use_entity_extraction: bool = False,
) -> LightRAG:
    """
    Creates and initializes a LightRAG instance pointing to a specific directory.
    Optionally enables entity extraction.
    """
    rag = LightRAG(
        working_dir=storage_dir,
        embedding_func=embedding_func,
        llm_model_func=OllamaLLM(),
        entity_extract_max_gleaning=config.ENTITY_EXTRACT_MAX_GLEANING if use_entity_extraction else 0,
    )
    await rag.initialize_storages()
    await initialize_pipeline_status()
    return rag


async def build_separated_vector_dbs(docs_by_subdomain: Dict[str, List[Document]]):
    """
    Builds one vector database per subdomain.
    Each will be written to a separate folder under BASE_STORAGE_DIR.
    """
    log.info(f"--- Running in VECTOR mode: Creating {len(docs_by_subdomain)} separated vector databases ---")
    successful, failed = 0, 0

    with Progress(*config.PROGRESS_COLUMNS) as progress:
        task_id = progress.add_task("[bold green]Vector DB Progress", total=len(docs_by_subdomain))

        for subdomain, docs in sorted(docs_by_subdomain.items()):
            progress.update(task_id, description=f"Processing: [cyan]{subdomain}")
            rag = None
            start = asyncio.get_event_loop().time()

            try:
                # Set up a storage directory for this subdomain
                storage_path = (config.BASE_STORAGE_DIR / subdomain).resolve()
                storage_path.mkdir(parents=True, exist_ok=True)

                # Initialize RAG pipeline for this subdomain
                rag = await init_rag_instance(storage_path.as_posix(), use_entity_extraction=False)

                # Extract text + file paths for indexing
                texts = [doc.page_content for doc in docs]
                paths = [doc.metadata.get("url", "source_unknown") for doc in docs]

                # Enqueue & process documents into chunks
                await rag.apipeline_enqueue_documents(texts, file_paths=paths)
                await rag.apipeline_process_enqueue_documents()

                # Count chunks written to vector store
                chunk_count = await rag._kv_storage.count(namespace="text_chunks")
                elapsed = asyncio.get_event_loop().time() - start

                log.info(
                    f"[bold green]✅ Finished '{subdomain}' — "
                    f"{len(docs)} docs → {chunk_count} chunks in {elapsed:.2f}s\n"
                )
                successful += 1

            except Exception as e:
                log.exception(f"❌ FAILED to build vector DB for '{subdomain}': {e}")
                failed += 1

            finally:
                if rag:
                    await rag.finalize_storages()
                progress.update(task_id, advance=1)

    return successful, failed


async def build_unified_knowledge_graph(docs_by_subdomain: Dict[str, List[Document]]):
    """
    Builds a single knowledge graph from all documents across all subdomains.
    Slower, but results in a unified KG.
    """
    log.info("--- Running in KG mode: Creating unified knowledge graph ---")
    rag = None

    try:
        storage_path = config.UNIFIED_KG_DIR.resolve()
        storage_path.mkdir(parents=True, exist_ok=True)

        texts, paths = flatten_documents(docs_by_subdomain)
        log.info(f"Processing {len(texts)} total documents from {len(docs_by_subdomain)} subdomains...")

        rag = await init_rag_instance(storage_path.as_posix(), use_entity_extraction=True)

        await rag.apipeline_enqueue_documents(texts, file_paths=paths)
        await rag.apipeline_process_enqueue_documents()

        log.info("[bold green]✅ Unified Knowledge Graph built successfully.")
        return 1, 0

    except Exception as e:
        log.exception(f"❌ FAILED to build unified knowledge graph: {e}")
        return 0, 1

    finally:
        if rag:
            await rag.finalize_storages()


async def main(args):
    """
    Main entrypoint. Loads documents and dispatches either vector DB or KG build.
    """
    if config.MODE not in ['vectors', 'kg']:
        log.error("Invalid MODE. Use 'vectors' or 'kg'. Example: MODE=vectors python build_dbs.py")
        return

    log.info(f"--- Starting build in '{config.MODE.upper()}' mode ---")

    docs_from_mongo = load_documents_from_mongo()
    if not docs_from_mongo:
        log.warning("No documents loaded from MongoDB. Aborting.")
        return

    # Group documents by subdomain for isolated storage
    docs_by_subdomain: Dict[str, List[Document]] = defaultdict(list)
    for doc in docs_from_mongo:
        url = doc.metadata.get("url")
        subdomain = get_sanitized_subdomain(url)
        docs_by_subdomain[subdomain].append(doc)

    # Optional CLI filter
    if args.subdomain:
        filtered = {sd: docs_by_subdomain[sd] for sd in args.subdomain if sd in docs_by_subdomain}
        missing = set(args.subdomain) - set(filtered.keys())
        for m in missing:
            log.warning(f"Subdomain '{m}' not found.")
        if not filtered:
            log.error("None of the requested subdomains were found. Aborting.")
            return
        docs_by_subdomain = filtered
        log.info(f"Filtering to {list(docs_by_subdomain.keys())}")

    # Run the selected build mode
    if config.MODE == 'vectors':
        success, fail = await build_separated_vector_dbs(docs_by_subdomain)
    else:
        success, fail = await build_unified_knowledge_graph(docs_by_subdomain)

    log.info(f"✅ {success} build(s) succeeded.")
    if fail > 0:
        log.warning(f"❌ {fail} build(s) failed.")



if __name__ == "__main__":
    # CLI entrypoint with optional --subdomain filter
    parser = argparse.ArgumentParser(description="Build RAG databases from MongoDB.")
    parser.add_argument("--subdomain", action="append", type=str, help="Process only one specific subdomain.", default=None)
    args = parser.parse_args()
    asyncio.run(main(args))

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
from lightrag.lightrag import LightRAG
from lightrag.kg.shared_storage import initialize_pipeline_status

import config
from utils.chunker import create_structured_chunks
from utils.mongo_loader import load_documents_from_mongo
from utils.subdomain_utils import get_sanitized_subdomain
from utils.local_models import embedding_func, OllamaLLM
from utils.debug_utils import log_config_summary

# Setup logging format and output
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)
log = logging.getLogger(__name__)


def flatten_documents(docs_by_subdomain: Dict[str, List[Document]]) -> List[Document]:
    """
    Flattens a nested dict of subdomain -> docs into a single list of Document objects.
    """
    return [doc for docs in docs_by_subdomain.values() for doc in docs]


async def init_rag_instance(
    storage_dir: str,
    vector_only: bool = False,
) -> LightRAG:
    """
    Creates and initializes a LightRAG instance.
    If vector_only=True, disables KG (no entity extraction, no graph storage).
    If vector_only=False, full KG mode with graph storage and entity extraction.
    """
    # In vector_only mode, we still need an LLM for LightRAG's structure,
    # but we disable the part that uses it for entity extraction.
    rag = LightRAG(
        working_dir=storage_dir,
        embedding_func=embedding_func,
        llm_model_func=OllamaLLM(),
        entity_extract_max_gleaning=0 if vector_only else 1,
    )
    await rag.initialize_storages()
    await initialize_pipeline_status()
    return rag


async def build_separated_vector_dbs(docs_by_subdomain: Dict[str, List[Document]]):
    """
    Builds one vector database per subdomain using structured chunking.
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
                storage_path = (config.BASE_STORAGE_DIR / subdomain).resolve()
                storage_path.mkdir(parents=True, exist_ok=True)
                rag = await init_rag_instance(storage_path.as_posix(), vector_only=True)

                log.info(f"Applying structured chunking for '{subdomain}'...")
                structured_chunks = create_structured_chunks(docs)
                log.info(f"Split {len(docs)} documents into {len(structured_chunks)} structured chunks.")

                texts = [chunk.page_content for chunk in structured_chunks]
                paths = [chunk.metadata.get("url", "source_unknown") for chunk in structured_chunks]
                
                await rag.apipeline_enqueue_documents(texts, file_paths=paths)
                await rag.apipeline_process_enqueue_documents()

                chunk_count = len(structured_chunks)
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
    Builds a single knowledge graph from all documents using structured chunking.
    """
    log.info("--- Running in KG mode: Creating unified knowledge graph ---")
    rag = None

    try:
        storage_path = config.UNIFIED_KG_DIR.resolve()
        storage_path.mkdir(parents=True, exist_ok=True)
        rag = await init_rag_instance(storage_path.as_posix(), vector_only=False)

        all_docs = flatten_documents(docs_by_subdomain)
        log.info(f"Processing {len(all_docs)} total documents from {len(docs_by_subdomain)} subdomains...")

        log.info("Applying structured chunking for unified KG...")
        structured_chunks = create_structured_chunks(all_docs)
        log.info(f"Split {len(all_docs)} documents into {len(structured_chunks)} structured chunks.")

        texts = [chunk.page_content for chunk in structured_chunks]
        paths = [chunk.metadata.get("url", "source_unknown") for chunk in structured_chunks]

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
    log_config_summary()

    if config.MODE not in ['vectors', 'kg']:
        log.error("Invalid MODE. Use 'vectors' or 'kg'. Example: MODE=vectors python build_dbs.py")
        return

    docs_from_mongo = load_documents_from_mongo()
    if not docs_from_mongo:
        log.warning("No documents loaded from MongoDB. Aborting.")
        return

    docs_by_subdomain: Dict[str, List[Document]] = defaultdict(list)
    for doc in docs_from_mongo:
        url = doc.metadata.get("url")
        subdomain = get_sanitized_subdomain(url)
        docs_by_subdomain[subdomain].append(doc)

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

    if config.MODE == 'vectors':
        success, fail = await build_separated_vector_dbs(docs_by_subdomain)
    else:
        success, fail = await build_unified_knowledge_graph(docs_by_subdomain)

    log.info(f"✅ {success} build(s) succeeded.")
    if fail > 0:
        log.warning(f"❌ {fail} build(s) failed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build RAG databases from MongoDB.")
    parser.add_argument("--subdomain", action="append", type=str, help="Process only one specific subdomain.", default=None)
    args = parser.parse_args()
    asyncio.run(main(args))

import os

os.environ["TOKENIZERS_PARALLELISM"] = "false"

import asyncio
import logging
import argparse
from pathlib import Path
from collections import defaultdict
from typing import List, Dict

from rich.logging import RichHandler
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn, SpinnerColumn

from langchain.docstore.document import Document
from lightrag.kg.shared_storage import initialize_pipeline_status
from lightrag.lightrag import LightRAG

from mongo_loader import load_documents_from_mongo
from utils.subdomain_utils import get_sanitized_subdomain
from local_models import embedding_func, OllamaLLM

logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)
log = logging.getLogger(__name__)

BASE_STORAGE_DIR = Path("../RAG_STORAGE")

MODE = os.getenv("MODE", "vectors").lower() # all,vectors


async def build_separated_vector_dbs(docs_by_subdomain: Dict[str, List[Document]]):
    """
    MODE=vectors
    Creates a separate vector database for each subdomain and reports the number of chunks and time taken.
    """
    log.info(f"--- Running in VECTOR mode: Creating {len(docs_by_subdomain)} separated vector databases ---")
    successful_builds, failed_builds = 0, 0

    progress_columns = [
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[bold blue]{task.completed}/{task.total}"),
        TextColumn("• Elapsed:"),
        TimeElapsedColumn(),
        TextColumn("• Remaining:"),
        TimeRemainingColumn(),
    ]

    with Progress(*progress_columns) as progress:
        task_id = progress.add_task("[bold green]Vector DB Progress", total=len(docs_by_subdomain))
        
        for subdomain, docs in sorted(docs_by_subdomain.items()):
            progress.update(task_id, description=f"Processing: [cyan]{subdomain}")
            rag_instance = None
            
            start_time = asyncio.get_event_loop().time()
            
            try:
                log.info(f"Building VECTOR DB for '{subdomain}' ({len(docs)} docs)...")
                storage_dir = BASE_STORAGE_DIR / subdomain
                storage_dir.mkdir(parents=True, exist_ok=True)

                rag_instance = LightRAG(
                    working_dir=storage_dir.resolve().as_posix(),
                    embedding_func=embedding_func,
                    llm_model_func=OllamaLLM(),
                    entity_extract_max_gleaning=0,
                )
                await rag_instance.initialize_storages()
                await initialize_pipeline_status()
                
                texts = [doc.page_content for doc in docs]
                file_paths = [doc.metadata.get("url", "source_unknown") for doc in docs]

                await rag_instance.apipeline_enqueue_documents(texts, file_paths=file_paths)
                await rag_instance.apipeline_process_enqueue_documents()
                
                chunk_count = await rag_instance._kv_storage.count(namespace="text_chunks")
                
                end_time = asyncio.get_event_loop().time()
                duration = end_time - start_time
                log.info(
                    f"[bold green]✅ Finished '{subdomain}'. "
                    f"Processed {len(docs)} documents into {chunk_count} chunks in {duration:.2f} seconds.\n"
                )
                successful_builds += 1
            except Exception as e:
                log.exception(f"❌ FAILED to build vector DB for '{subdomain}': {e}")
                failed_builds += 1
            finally:
                if rag_instance:
                    await rag_instance.finalize_storages()
                progress.update(task_id, advance=1)
    
    return successful_builds, failed_builds

async def build_unified_knowledge_graph(docs_by_subdomain: Dict[str, List[Document]]):
    """
    MODE=kg
    Builds one single, unified Knowledge Graph from ALL documents across ALL subdomains.
    """
    log.info("--- Running in KG mode: Creating one unified knowledge graph ---")
    rag_instance = None
    try:
        kg_storage_dir = BASE_STORAGE_DIR / "_UNIFIED_KG"
        kg_storage_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"All knowledge graph data will be stored in: {kg_storage_dir}")
        
        all_texts = []
        all_file_paths = []
        total_docs = 0
        for subdomain, docs in docs_by_subdomain.items():
            total_docs += len(docs)
            all_texts.extend([doc.page_content for doc in docs])
            all_file_paths.extend([doc.metadata.get("url", "source_unknown") for doc in docs])
        
        log.info(f"Processing {total_docs} total documents from {len(docs_by_subdomain)} subdomains...")

        rag_instance = LightRAG(
            working_dir=kg_storage_dir.resolve().as_posix(),
            embedding_func=embedding_func,
            llm_model_func=OllamaLLM(),
        )
        await rag_instance.initialize_storages()
        await initialize_pipeline_status()

        log.info("Enqueuing all documents... This may take a moment.")
        await rag_instance.apipeline_enqueue_documents(all_texts, file_paths=all_file_paths)

        log.info("Building the unified knowledge graph... This will be very slow.")
        await rag_instance.apipeline_process_enqueue_documents()

        log.info("[bold green]✅ Unified Knowledge Graph has been built successfully.")
        return 1, 0
        
    except Exception as e:
        log.exception(f"❌ FAILED to build the unified knowledge graph: {e}")
        return 0, 1
    finally:
        if rag_instance:
            await rag_instance.finalize_storages()


async def main(args):
    """Main orchestrator that loads data and runs the selected build mode."""
    if MODE not in ['vectors', 'kg']:
        log.error("Invalid MODE. Please set the environment variable to 'vectors' or 'kg'.")
        log.info("Example: MODE=vectors python your_script_name.py")
        return

    log.info(f"--- Starting RAG Database Build Process in '{MODE.upper()}' MODE ---")
    docs_from_mongo = load_documents_from_mongo()
    if not docs_from_mongo:
        log.warning("No documents loaded from MongoDB. Aborting build.")
        return

    docs_by_subdomain: Dict[str, List[Document]] = defaultdict(list)
    for doc in docs_from_mongo:
        url = doc.metadata.get("url")
        subdomain_name = get_sanitized_subdomain(url)
        docs_by_subdomain[subdomain_name].append(doc)

    if args.subdomain:
        if args.subdomain in docs_by_subdomain:
            log.info(f"Filtering to process only the specified subdomain: '{args.subdomain}'")
            docs_by_subdomain = {args.subdomain: docs_by_subdomain[args.subdomain]}
        else:
            log.error(f"Subdomain '{args.subdomain}' not found.")
            return

    successful_builds, failed_builds = 0, 0
    if MODE == 'vectors':
        successful_builds, failed_builds = await build_separated_vector_dbs(docs_by_subdomain)
    elif MODE == 'kg':
        successful_builds, failed_builds = await build_unified_knowledge_graph(docs_by_subdomain)
    
    log.info(f"--- Build Process Finished for MODE '{MODE.upper()}' ---")
    log.info(f"✅ Successful builds: {successful_builds}.")
    if failed_builds > 0:
        log.warning(f"❌ Failed builds: {failed_builds}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build RAG databases from MongoDB.")
    parser.add_argument("--subdomain", type=str, help="Optional: Process only a single specified subdomain.", default=None)
    args = parser.parse_args()
    asyncio.run(main(args))
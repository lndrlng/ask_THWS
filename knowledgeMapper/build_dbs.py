import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"  # Avoids excessive parallelism warnings

import asyncio
import logging
import argparse
import threading
import time
import json
from collections import defaultdict
from typing import List, Dict
from pathlib import Path

from rich.logging import RichHandler
from rich.progress import Progress
from langchain.docstore.document import Document
from lightrag.lightrag import LightRAG

import config
from utils.chunker import create_structured_chunks
from utils.mongo_loader import load_documents_from_mongo
from utils.subdomain_utils import get_sanitized_subdomain
from utils.local_models import embedding_func, OllamaLLM

logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)
log = logging.getLogger(__name__)

def monitor_processing_progress(
    stop_event: threading.Event,
    progress: Progress,
    task_id,
    status_file_path: str,
    description: str
):
    """Monitors the doc_status.json file and updates a rich progress bar."""
    time.sleep(2) 
    
    while not stop_event.is_set():
        try:
            with open(status_file_path, "r", encoding='utf-8') as f:
                status_data = json.load(f)
            
            total_docs = len(status_data)
            processed_docs = sum(1 for doc in status_data.values() if doc.get("status") != "pending")
            
            progress.update(
                task_id,
                total=total_docs,
                completed=processed_docs,
                description=description
            )
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(1)
            continue
        except Exception as e:
            log.error(f"Error in monitor thread: {e}")

        time.sleep(1) 

async def dummy_llm(*args, **kwargs):
    """A dummy async function that does nothing, used to disable LLM calls."""
    return ""

async def init_rag_instance(
    storage_dir: str,
    use_entity_extraction: bool = False,
) -> LightRAG:
    """
    Creates and initializes a LightRAG instance. In vectors mode, it uses a
    dummy LLM to reliably disable entity extraction.
    """
    llm_instance = OllamaLLM() if use_entity_extraction else dummy_llm
    gleaning_value = config.ENTITY_EXTRACT_MAX_GLEANING if use_entity_extraction else 0

    rag = LightRAG(
        working_dir=storage_dir,
        embedding_func=embedding_func,
        llm_model_func=llm_instance,
        entity_extract_max_gleaning=gleaning_value,
    )
    await rag.initialize_storages()
    
    if use_entity_extraction:
        from lightrag.kg.shared_storage import initialize_pipeline_status
        await initialize_pipeline_status()
        
    return rag

def flatten_documents(docs_by_subdomain: Dict[str, List[Document]]) -> List[Document]:
    """Flattens a nested dict of subdomain -> docs into a single list of docs."""
    return [doc for docs in docs_by_subdomain.values() for doc in docs]

async def build_separated_vector_dbs(docs_by_subdomain: Dict[str, List[Document]]):
    """Builds one vector database per subdomain with detailed progress monitoring."""
    log.info(f"--- Running in VECTORS mode: Creating {len(docs_by_subdomain)} separated vector databases ---")
    successful, failed = 0, 0

    with Progress(*config.PROGRESS_COLUMNS, transient=True) as progress:
        overall_task = progress.add_task("[bold green]Overall Subdomain Progress", total=len(docs_by_subdomain))

        for subdomain, docs in sorted(docs_by_subdomain.items()):
            rag = None
            try:
                storage_path = (config.BASE_STORAGE_DIR / subdomain).resolve()
                storage_path.mkdir(parents=True, exist_ok=True)
                rag = await init_rag_instance(str(storage_path), use_entity_extraction=False)

                log.info(f"Applying structured chunking for '{subdomain}'...")
                structured_chunks = create_structured_chunks(docs)
                texts = [chunk.page_content for chunk in structured_chunks]
                paths = [chunk.metadata.get("url", "source_unknown") for chunk in structured_chunks]
                
                await rag.apipeline_enqueue_documents(texts, file_paths=paths)

                doc_processing_task = progress.add_task(f"Initializing '{subdomain}'...", total=None)
                status_file = storage_path / "kv_store_doc_status.json"
                stop_monitoring = threading.Event()
                
                monitor_thread = threading.Thread(
                    target=monitor_processing_progress,
                    args=(stop_monitoring, progress, doc_processing_task, str(status_file), f"[cyan]Processing docs for [bold yellow]{subdomain}[/bold yellow]"),
                    daemon=True
                )
                monitor_thread.start()

                await rag.apipeline_process_enqueue_documents()

                stop_monitoring.set()
                monitor_thread.join(timeout=2)
                
                final_count = len(rag.text_storage.get_all_documents())
                progress.update(doc_processing_task, completed=final_count, total=final_count, description=f"[bold green]✓ '{subdomain}' complete[/bold green]")

                log.info(f"[bold green]✅ Finished '{subdomain}' — {len(docs)} docs → {len(structured_chunks)} chunks.\n")
                successful += 1

            except Exception as e:
                log.exception(f"❌ FAILED to build vector DB for '{subdomain}': {e}")
                failed += 1
            finally:
                if rag:
                    await rag.finalize_storages()
                progress.update(overall_task, advance=1)

    return successful, failed

async def build_unified_knowledge_graph(docs_by_subdomain: Dict[str, List[Document]]):
    """Builds a single knowledge graph with detailed progress monitoring."""
    log.info("--- Running in KG mode: Creating a unified knowledge graph ---")
    rag = None
    try:
        storage_path = config.UNIFIED_KG_DIR.resolve()
        storage_path.mkdir(parents=True, exist_ok=True)
        rag = await init_rag_instance(str(storage_path), use_entity_extraction=True)

        all_docs = flatten_documents(docs_by_subdomain)
        total_doc_count = len(all_docs)
        log.info(f"Processing {total_doc_count} total documents from {len(docs_by_subdomain)} subdomains...")

        log.info("Applying structured chunking for unified KG...")
        structured_chunks = create_structured_chunks(all_docs)
        log.info(f"Split {total_doc_count} documents into {len(structured_chunks)} structured chunks.")
        
        texts = [chunk.page_content for chunk in structured_chunks]
        paths = [chunk.metadata.get("url", "source_unknown") for chunk in structured_chunks]

        await rag.apipeline_enqueue_documents(texts, file_paths=paths)
        
        with Progress(*config.PROGRESS_COLUMNS, transient=True) as progress:
            doc_processing_task = progress.add_task(f"[cyan]Building Knowledge Graph...", total=total_doc_count)
            status_file = storage_path / "kv_store_doc_status.json"
            stop_monitoring = threading.Event()
            
            monitor_thread = threading.Thread(
                target=monitor_processing_progress,
                args=(stop_monitoring, progress, doc_processing_task, str(status_file), "[cyan]Building Knowledge Graph..."),
                daemon=True
            )
            monitor_thread.start()

            await rag.apipeline_process_enqueue_documents()

            stop_monitoring.set()
            monitor_thread.join(timeout=2)
            
            final_count = len(rag.text_storage.get_all_documents())
            progress.update(doc_processing_task, completed=final_count, total=final_count, description="[bold green]✓ Knowledge Graph build complete[/bold green]")

        log.info("[bold green]✅ Unified Knowledge Graph built successfully.")
        return 1, 0

    except Exception as e:
        log.exception(f"❌ FAILED to build unified knowledge graph: {e}")
        return 0, 1
    finally:
        if rag:
            await rag.finalize_storages()

async def main(args):
    """Main entrypoint. Loads documents and dispatches build."""
    if config.MODE not in ['vectors', 'kg']:
        log.error("Invalid MODE. Use 'vectors' or 'kg'. Example: MODE=vectors python build_dbs.py")
        return

    log.info(f"--- Starting build in '{config.MODE.upper()}' mode ---")

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
        log.info(f"Filtering to process only: {list(docs_by_subdomain.keys())}")

    if config.MODE == 'vectors':
        success, fail = await build_separated_vector_dbs(docs_by_subdomain)
    else: # config.MODE == 'kg'
        success, fail = await build_unified_knowledge_graph(docs_by_subdomain)

    log.info(f"✅ {success} build(s) succeeded.")
    if fail > 0:
        log.warning(f"❌ {fail} build(s) failed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build RAG databases from MongoDB.")
    parser.add_argument("--subdomain", action="append", type=str, help="Process only one specific subdomain.", default=None)
    args = parser.parse_args()
    asyncio.run(main(args))
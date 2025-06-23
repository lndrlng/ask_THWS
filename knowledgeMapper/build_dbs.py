import os

os.environ["TOKENIZERS_PARALLELISM"] = "false"

import asyncio
import logging
import argparse
from pathlib import Path
from collections import defaultdict
from typing import List, Dict

from rich.logging import RichHandler
from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    SpinnerColumn,
)

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

BASE_STORAGE_DIR = Path("../rag_storage_hku_separated")


async def process_subdomain(subdomain: str, docs: List[Document]):
    """
    A much simpler function to process all documents for a single subdomain.
    It no longer manages its own progress bar.
    """
    rag_instance = None
    try:
        log.info(f"Building database for '{subdomain}' ({len(docs)} docs).")

        subdomain_storage_dir = BASE_STORAGE_DIR / subdomain
        subdomain_storage_dir.mkdir(parents=True, exist_ok=True)

        rag_instance = LightRAG(
            working_dir=subdomain_storage_dir.resolve().as_posix(),
            embedding_func=embedding_func,
            llm_model_func=OllamaLLM(),
        )

        await rag_instance.initialize_storages()
        await initialize_pipeline_status()

        texts = [doc.page_content for doc in docs]
        file_paths = [doc.metadata.get("url", "source_unknown") for doc in docs]

        await rag_instance.apipeline_enqueue_documents(texts, file_paths=file_paths)
        
        await rag_instance.apipeline_process_enqueue_documents()

        return True

    except Exception as e:
        log.exception(f"❌ FAILED to process subdomain '{subdomain}': {e}")
        return False
    finally:
        if rag_instance:
            await rag_instance.finalize_storages()


async def main(args):
    """Main orchestrator that loads all data and processes subdomains sequentially."""
    log.info("--- Starting RAG Database Build Process ---")
    docs_from_mongo = load_documents_from_mongo()
    if not docs_from_mongo:
        log.warning("No documents loaded from MongoDB. Aborting build.")
        return

    docs_by_subdomain: Dict[str, List[Document]] = defaultdict(list)
    for doc in docs_from_mongo:
        url = doc.metadata.get("url")
        subdomain_name = get_sanitized_subdomain(url)
        if not subdomain_name or subdomain_name == "default":
            log.warning(
                f"Document with missing/invalid URL found (mongo_id: {doc.metadata.get('mongo_id')}). Assigning to 'default' subdomain."
            )
            subdomain_name = "default"
        docs_by_subdomain[subdomain_name].append(doc)

    if args.subdomain:
        if args.subdomain in docs_by_subdomain:
            log.info(f"Filtering to process only the specified subdomain: '{args.subdomain}'")
            docs_by_subdomain = {args.subdomain: docs_by_subdomain[args.subdomain]}
        else:
            log.error(
                f"Subdomain '{args.subdomain}' not found. Available: {list(docs_by_subdomain.keys())}"
            )
            return

    log.info(f"Found {len(docs_by_subdomain)} subdomains to process.")

    successful_builds = 0
    failed_builds = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[bold blue]{task.completed}/{task.total}"),
        "[",
        TimeElapsedColumn(),
        "<",
        TimeRemainingColumn(),
        "]",
    ) as progress:
        overall_task_id = progress.add_task(
            "[bold green]Overall Progress", total=len(docs_by_subdomain)
        )

        for subdomain, docs in sorted(docs_by_subdomain.items()):
            progress.update(overall_task_id, description=f"Processing: [cyan]{subdomain}")
            
            success = await process_subdomain(subdomain, docs)
            
            if success:
                successful_builds += 1
                log.info(f"[bold green]✅ Success! Finished subdomain '{subdomain}'.[/bold green]\n")
            else:
                failed_builds += 1
            
            progress.update(overall_task_id, advance=1)
        
        progress.update(overall_task_id, description="[bold green]All subdomains processed.")


    log.info("--- RAG Database Build Process Finished ---")
    s_succ = "s" if successful_builds != 1 else ""
    log.info(f"✅ Successfully processed {successful_builds} subdomain{s_succ}.")
    if failed_builds > 0:
        s_fail = "s" if failed_builds != 1 else ""
        log.warning(
            f"❌ Failed to process {failed_builds} subdomain{s_fail}. Check logs for details."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build RAG databases from MongoDB.")
    parser.add_argument(
        "--subdomain",
        type=str,
        help="Optional: Process only a single specified subdomain.",
        default=None,
    )
    args = parser.parse_args()

    os.environ["MUPDF_WARNING_PREFIX"] = "!"
    asyncio.run(main(args))
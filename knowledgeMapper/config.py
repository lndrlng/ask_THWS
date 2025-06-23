import os
from pathlib import Path
from rich.progress import (
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

# --- Application Mode ---
# Sets the primary operation mode: 'vectors' or 'kg'.
MODE = os.getenv("MODE", "vectors").lower()

# --- Storage Configuration ---
BASE_STORAGE_DIR = Path("../RAG_STORAGE")
UNIFIED_KG_DIR = BASE_STORAGE_DIR / "_UNIFIED_KG"

# --- MongoDB Configuration ---
MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
MONGO_PORT = int(os.getenv("MONGO_PORT", 27017))
MONGO_DB_NAME = "askthws_scraper"
MONGO_USER = os.getenv("MONGO_USER", "scraper")
MONGO_PASS = os.getenv("MONGO_PASS", "password")
MONGO_PAGES_COLLECTION = "pages"
MONGO_FILES_COLLECTION = "files"

# --- AI Model Configuration ---
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
EMBEDDING_DEVICE = "cuda"
EMBEDDING_BATCH_SIZE = 16
EMBEDDING_CONCURRENCY = 2

OLLAMA_MODEL_NAME = "mistral"
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_NUM_CTX = 16384
OLLAMA_NUM_PREDICT = 4096

# --- LightRAG Processing Settings ---
ENTITY_EXTRACT_MAX_GLEANING = 0 # Set to 0 to disable LLM-based entity extraction

# --- UI & Logging Configuration ---
PROGRESS_COLUMNS = [
    SpinnerColumn(),
    TextColumn("[progress.description]{task.description}"),
    BarColumn(),
    TextColumn("[bold blue]{task.completed}/{task.total}"),
    TextColumn("• Elapsed:"),
    TimeElapsedColumn(),
    TextColumn("• Remaining:"),
    TimeRemainingColumn(),
]
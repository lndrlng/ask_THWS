import os
from pathlib import Path
from rich.progress import (
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

# Application mode: either 'vectors' or 'kg'
MODE = os.getenv("MODE", "vectors").lower()

# Language selection for filtering documents (used in mongo_loader or processing)
LANGUAGE = os.getenv("LANGUAGE", "de").lower()  # 'all', 'de', or 'en'

# Directory for all vector/graph storage
BASE_STORAGE_DIR = Path("../RAG_STORAGE")
UNIFIED_KG_DIR = BASE_STORAGE_DIR / "_UNIFIED_KG"

# MongoDB connection config
MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
MONGO_PORT = int(os.getenv("MONGO_PORT", 27017))
MONGO_DB_NAME = "askthws_scraper"
MONGO_USER = os.getenv("MONGO_USER", "scraper")
MONGO_PASS = os.getenv("MONGO_PASS", "password")
MONGO_PAGES_COLLECTION = "pages"
MONGO_FILES_COLLECTION = "files"

# Embedding model settings
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
EMBEDDING_DEVICE = "cuda"
EMBEDDING_BATCH_SIZE = 16
EMBEDDING_CONCURRENCY = 2  # Controls number of concurrent embedding jobs

# LLM configuration (e.g., for Ollama server)
OLLAMA_MODEL_NAME = "mistral"
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_NUM_CTX = 16384
OLLAMA_NUM_PREDICT = 4096

# Controls LightRAG's entity extraction feature (0 disables it)
ENTITY_EXTRACT_MAX_GLEANING = 30

# Rich CLI progress bar formatting
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

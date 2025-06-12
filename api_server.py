# File: api_server.py

import time
import torch
import subprocess
import atexit
import os
import signal
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from requests.exceptions import HTTPError

# Assuming lightrag is installed from git+https://github.com/HKUDS/LightRAG.git
# This version of LightRAG has a different structure, so we only import what's available.
from lightrag import LightRAG, QueryParam
# We assume these are your custom wrapper classes defined within your project
# and are designed to work with HKUDS/LightRAG.
from knowledgeMapper.local_models import HFEmbedFunc, OllamaLLM

# --- Device Info ---
# Determine the computation device based on availability
device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
print(f"🔥 Using device: {device}")


# --- LightRAG Setup ---
# Initialize the main LightRAG object from the HKUDS library.
# The model name (e.g., "mistral") must be configured inside your OllamaLLM class.
print("🧠 Initializing LightRAG...")
rag = LightRAG(
    working_dir="./rag_storage",
    embedding_func=HFEmbedFunc(),
    llm_model_func=OllamaLLM() # OllamaLLM must be configured internally
)

# --- Lifespan for Startup and Shutdown Events ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup and shutdown events for the FastAPI application.
    Initializes LightRAG storages on startup.
    """
    # Code to run on startup
    print("🚀 Initializing LightRAG storages...")
    await rag.initialize_storages()
    print("✅ LightRAG storages initialized.")
    yield
    # Code to run on shutdown
    print("FastAPI app is shutting down.")


# --- FastAPI App Initialization ---
# We now use the lifespan context manager for startup events.
app = FastAPI(
    title="LightRAG API Server",
    description="An API for querying a Retrieval-Augmented Generation system.",
    version="1.0.0",
    lifespan=lifespan
)

class Question(BaseModel):
    """Pydantic model for the input question."""
    query: str

# --- Ollama Background Server Management ---
# Start the Ollama server in a background process.
# Using DEVNULL to hide the verbose output from the server.
print("🚓 Starting Ollama server in the background...")
ollama_process = subprocess.Popen(
    ["ollama", "serve"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    preexec_fn=os.setsid if os.name != 'nt' else None # Necessary for proper termination on Unix-like systems
)

def shutdown_ollama():
    """Function to gracefully shut down the Ollama server process."""
    print("Shutting down Ollama server...")
    if ollama_process:
        try:
            # On Windows, terminate is sufficient.
            if os.name == 'nt':
                ollama_process.terminate()
            # On Unix-like systems, we kill the entire process group to ensure it's gone.
            else:
                os.killpg(os.getpgid(ollama_process.pid), signal.SIGTERM)
            ollama_process.wait(timeout=5)
            print("🚓 Ollama server stopped successfully.")
        except (ProcessLookupError, OSError, subprocess.TimeoutExpired) as e:
            print(f"Could not stop Ollama server gracefully: {e}. It might have already been stopped.")

# Register the shutdown function to be called on script exit.
atexit.register(shutdown_ollama)

# --- API Endpoints ---

@app.post("/ask")
async def ask(data: Question):
    """
    Main endpoint to ask a question using the full LightRAG hybrid retrieval.
    This combines knowledge graph and vector search capabilities.
    """
    start = time.time()
    print(f"Received query: '{data.query}'")
    try:
        # Perform the query using the hybrid mode
        result = await rag.aquery(data.query, param=QueryParam(mode="hybrid"))
        duration = round(time.time() - start, 2)

        # The `rag.aquery` from this library version returns the answer directly as a string.
        # It does not return a structured object with source documents.
        answer_text = result if isinstance(result, str) else ""

        # Since source documents are not returned, we provide an empty list.
        source_metadata = []

        print(f"Answer generated in {duration} seconds.")
        return {
            "question": data.query,
            "answer": answer_text,
            "sources": source_metadata,
            "mode": "lightrag+hybrid",
            "duration_seconds": duration,
        }
    except HTTPError as e:
        # This catches errors from the Ollama backend (like 404 Not Found)
        print(f"ERROR: An HTTP error occurred while communicating with the LLM backend: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"The LLM backend is unavailable or could not find the requested model. Details: {e}"
        )
    except Exception as e:
        # This catches any other unexpected errors during the RAG process.
        print(f"ERROR: An unexpected error occurred: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"An internal server error occurred. Please check the server logs. Details: {e}"
        )

@app.post("/ask-raw")
def ask_raw(data: Question):
    """A simple echo endpoint for debugging and testing connectivity."""
    return {
        "question": data.query,
        "echo": data.query,
        "mode": "raw-debug"
    }

@app.get("/metadata")
def metadata():
    """Returns metadata about the running service and models."""
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).strip().decode("utf-8")
    except (subprocess.CalledProcessError, FileNotFoundError):
        commit = "N/A"

    return {
        "embedding_model": HFEmbedFunc.__name__,
        "llm_model": OllamaLLM.__name__,
        "git_commit": commit,
        "device": device,
        "retriever": "LightRAG Hybrid (from HKUDS/LightRAG)"
    }

@app.get("/")
def read_root():
    """Root endpoint providing basic information about the API."""
    return {"message": "Welcome to the LightRAG API. Use the /docs endpoint to see the API documentation."}

# --- Run FastAPI Server ---
if __name__ == "__main__":
    print("Starting FastAPI server...")
    # The module name here must match the filename (api_server.py -> "api_server")
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=False)

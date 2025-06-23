import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from retrieval import execute_multi_subdomain_retrieval
import subprocess
import atexit
import os
import signal

# --- Ollama Background Server Management ---
print("🚓 Starting Ollama server in the background...")
ollama_process = subprocess.Popen(
    ["ollama", "serve"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    preexec_fn=os.setsid if os.name != "nt" else None,
)


@atexit.register
def shutdown_ollama():
    """Function to gracefully shut down the Ollama server process."""
    print("Shutting down Ollama server...")
    if ollama_process:
        try:
            if os.name == "nt":
                ollama_process.terminate()
            else:
                os.killpg(os.getpgid(ollama_process.pid), signal.SIGTERM)
            ollama_process.wait(timeout=5)
            print("🚓 Ollama server stopped successfully.")
        except Exception as e:
            print(f"Could not stop Ollama server gracefully: {e}")


# --- FastAPI App Initialization ---
app = FastAPI(
    title="Hybrid RAG API",
    description="API for querying multiple subdomain databases with a shared knowledge graph.",
    version="20.0.0",
)


class QueryRequest(BaseModel):
    query: str
    # Example: ["www_thws_de", "fwi_fhws_de"]
    subdomains: List[str]


@app.post("/ask")
async def ask(data: QueryRequest):
    """
    Performs a RAG query against one or more subdomains.
    The first subdomain in the list is treated as primary.
    """
    try:
        result = await execute_multi_subdomain_retrieval(
            user_query=data.query, subdomains=data.subdomains
        )
        return result
    except ValueError as e:
        # This catches errors from rag_manager if a DB is not found
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")


@app.get("/")
def root():
    return {"message": "Hybrid RAG API is running."}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

# File: api_server.py
# WORKAROUND version: Implements a Translate -> Query -> Translate pipeline to handle a mixed-language KG.

import time
import torch
import subprocess
import atexit
import os
import signal
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from requests.exceptions import HTTPError
from typing import List

# --- Import components from our local_models ---
from knowledgeMapper.local_models import (
    load_models,
    get_llm,
    HFEmbedFunc,
    OllamaLLM_Func,
    OllamaLLM, # Import the class for type hinting
)
# --- Import components from the lightrag library ---
from lightrag import LightRAG
from lightrag.base import QueryParam # Correct import based on provided source
# This import is required for the mandatory initialization step.
from lightrag.kg.shared_storage import initialize_pipeline_status


# --- Device Info ---
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"🔥 Using device: {device}")


# --- Lifespan to load all models and initialize LightRAG ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup events. Initializes models first, then LightRAG.
    """
    print("🚀 Server starting up...")
    load_models()
    print("🧠 Initializing LightRAG framework...")
    rag = LightRAG(
        working_dir="./rag_storage",
        embedding_func=HFEmbedFunc(),
        llm_model_func=OllamaLLM_Func()
    )
    app.state.rag = rag
    await rag.initialize_storages()
    print("✅ LightRAG storages initialized.")
    await initialize_pipeline_status()
    print("✅ LightRAG pipeline status initialized.")
    print("✅ Server is ready to accept requests.")
    yield
    print("🔌 Server shutting down.")


# --- FastAPI App Initialization ---
app = FastAPI(
    title="THWS KG-RAG API Server (Translation Workaround)",
    description="Ein API-Server, der eine Übersetzungs-Pipeline verwendet, um deutsche Antworten aus einer gemischtsprachigen Wissensdatenbank zu liefern.",
    version="5.5.0", # Version bump for workaround
    lifespan=lifespan
)


class Question(BaseModel):
    query: str


# --- Ollama Background Server Management (Unchanged) ---
print("🚓 Starting Ollama server in the background...")
ollama_process = subprocess.Popen(
    ["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    preexec_fn=os.setsid if os.name != 'nt' else None
)


@atexit.register
def shutdown_ollama():
    print("Shutting down Ollama server...")
    if ollama_process:
        try:
            if os.name == 'nt':
                ollama_process.terminate()
            else:
                os.killpg(os.getpgid(ollama_process.pid), signal.SIGTERM)
            ollama_process.wait(timeout=5)
            print("🚓 Ollama server stopped successfully.")
        except (ProcessLookupError, OSError, subprocess.TimeoutExpired) as e:
            print(f"Could not stop Ollama server gracefully: {e}")


# --- API Endpoints ---
@app.post("/ask")
async def ask(data: Question, request: Request):
    """
    Implements a Translate -> Query -> Translate pipeline.
    """
    start_time = time.time()
    print(f"\n--- New Request ---")
    print(f"Received German query: '{data.query}'")
    try:
        rag: LightRAG = request.app.state.rag
        llm: OllamaLLM = get_llm()

        # STEP 1: Translate German query to English for effective retrieval
        print("1. Translating query to English...")
        english_query = await llm.translate_to_english(data.query)
        print(f"   - English query for retrieval: '{english_query}'")

        # STEP 2: Prepare a custom ENGLISH prompt for the English KG context
        english_system_prompt = f"""
You are a specialized assistant for the THWS university.
Your task is to answer the user's question precisely and ONLY based on the provided context from the knowledge graph.
Ignore your general knowledge. Formulate a helpful, direct, and complete answer in ENGLISH.

User's Question: "{english_query}"

Knowledge Graph Context:
{{context_data}}

Instructions:
- Analyze the context carefully.
- Formulate a clear and direct answer to the user's question in English.
- If the information is not in the context, respond ONLY with: "Based on the provided documents, I could not find an answer."
- Append the sources, and add them to the final answer.

Answer:
"""

        # STEP 3: Query the KG in English
        print("2. Executing query with LightRAG in English...")
        params = QueryParam(mode="hybrid", user_prompt=english_system_prompt)
        english_answer = await rag.aquery(english_query, param=params)
        print(f"   - Intermediate English answer: '{english_answer}'")

        # Handle case where the model couldn't find an answer
        if "could not find an answer" in english_answer:
            print("   - No answer found in KG. Translating fallback message.")
            final_answer = "Die angefragten Informationen konnte ich in meiner Wissensdatenbank leider nicht finden."
        else:
            # STEP 4: Translate the English answer back to German
            print("3. Translating final answer to German...")
            final_answer = await llm.translate_to_german(english_answer)
            print(f"   - Final German answer: '{final_answer}'")


        duration = round(time.time() - start_time, 2)
        print(f"--- Request completed in {duration} seconds. ---")

        return {
            "question": data.query,
            "answer": final_answer,
            "sources": [],
            "mode": "translation_workaround_hybrid",
            "duration_seconds": duration,
        }
    except Exception as e:
        print(f"ERROR: An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error. Details: {e}")


@app.get("/")
def read_root():
    return {"message": "Welcome to the THWS KG-RAG API (Translation Workaround)."}


@app.get("/metadata")
def metadata(request: Request):
    """Provides metadata about the running service."""
    rag: LightRAG = request.app.state.rag
    retriever_info = rag.vector_storage

    from knowledgeMapper.local_models import EMBEDDING_MODEL_NAME, RERANKER_MODEL_NAME, OLLAMA_MODEL_NAME

    return {
        "embedding_model": EMBEDDING_MODEL_NAME,
        "reranker_model": RERANKER_MODEL_NAME,
        "llm_model": OLLAMA_MODEL_NAME,
        "device": device,
        "retriever_class": retriever_info
    }


# --- Run FastAPI Server ---
if __name__ == "__main__":
    print("Starting FastAPI server with uvicorn...")
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=False)

# File: rag_server.py

import time
import torch
import subprocess
import atexit
import os
import signal
from fastapi import FastAPI
from lightrag.components.model_client import OllamaClient
from pydantic import BaseModel
from lightrag import LightRAG, QueryParam
from knowledgeMapper.local_models import HFEmbedFunc, OllamaLLM
from lightrag.core import Component, Generator, DataClass
from lightrag.components.output_parsers import JsonOutputParser
from dataclasses import dataclass, field
import uvicorn

# --- Config ---
OLLAMA_MODEL = "mistral"

# --- Device Info ---
device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
print(f"🔥 Using device: {device}")

# --- FastAPI ---
app = FastAPI()

class Question(BaseModel):
    query: str

# --- Ollama Background Server (optional) ---
ollama_process = subprocess.Popen(
    ["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)

def shutdown_ollama():
    if os.name == 'nt':
        ollama_process.terminate()
    else:
        os.killpg(os.getpgid(ollama_process.pid), signal.SIGTERM)
    print("🚓 Ollama server stopped.")

atexit.register(shutdown_ollama)

# --- LightRAG Setup ---
rag = LightRAG(
    working_dir="./rag_storage",
    embedding_func=HFEmbedFunc(),
    llm_model_func=OllamaLLM()
)

@app.on_event("startup")
async def startup():
    print("🚀 Initializing LightRAG storages...")
    await rag.initialize_storages()

# --- Default Endpoint: Full LightRAG (graph + vector) ---
@app.post("/ask")
async def ask(data: Question):
    start = time.time()
    result = await rag.aquery(data.query, param=QueryParam(mode="hybrid"))
    duration = round(time.time() - start, 2)

    source_metadata = [doc.metadata for doc in result.source_documents]

    return {
        "question": data.query,
        "answer": result.output,
        "sources": source_metadata,
        "mode": "lightrag+hybrid",
        "duration_seconds": duration,
    }

# --- Light Template-Based (Component) ---
@dataclass
class QAOutput(DataClass):
    explanation: str = field(metadata={"desc": "Eine kurze Erklärung."})
    example: str = field(metadata={"desc": "Ein konkretes Beispiel."})

qa_template = r"""<SYS>
Du bist ein hilfreicher Assistent der THWS.
<OUTPUT_FORMAT>
{{output_format_str}}
</OUTPUT_FORMAT>
</SYS>
Frage: {{input_str}}
Antwort:"""

class QA(Component):
    def __init__(self):
        super().__init__()
        parser = JsonOutputParser(data_class=QAOutput, return_data_class=True)
        self.generator = Generator(
            model_client = OllamaClient.from_model(OLLAMA_MODEL),
            model_kwargs={},
            template=qa_template,
            prompt_kwargs={"output_format_str": parser.format_instructions()},
            output_processors=parser,
        )

    def call(self, query: str):
        return self.generator.call({"input_str": query})

    async def acall(self, query: str):
        return await self.generator.acall({"input_str": query})

qa_pipeline = QA()

@app.post("/ask-simple")
def ask_simple(data: Question):
    start = time.time()
    result = qa_pipeline.call(data.query)
    duration = round(time.time() - start, 2)
    return {
        "question": data.query,
        "answer": result.explanation,
        "example": result.example,
        "mode": "template-component",
        "duration_seconds": duration,
    }

# --- Raw Echo for Testing ---
@app.post("/ask-raw")
def ask_raw(data: Question):
    return {
        "question": data.query,
        "echo": data.query,
        "mode": "raw-debug"
    }

@app.get("/metadata")
def metadata():
    commit = subprocess.getoutput("git rev-parse HEAD")
    return {
        "embedding_model": HFEmbedFunc.__name__,
        "llm_model": f"ollama:{OLLAMA_MODEL}",
        "git_commit": commit,
        "device": device,
        "retriever": "LightRAG Hybrid"
    }

# --- Run FastAPI Server ---
if __name__ == "__main__":
    uvicorn.run("rag_server:app", host="0.0.0.0", port=8000, reload=False)
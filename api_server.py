import time
import torch
import requests
import warnings
import subprocess
import atexit
import os
import signal
from fastapi import FastAPI
from pydantic import BaseModel
from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from lightrag.core import Component, Generator, DataClass
from lightrag.components.model_client import OllamaClient
from lightrag.components.output_parsers import JsonOutputParser
from dataclasses import dataclass, field
import uvicorn

# --- Config ---
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "your_password"
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "thws_data2_chunks"
EMBED_MODEL_NAME = "BAAI/bge-m3"
OLLAMA_MODEL = "mistral"
TOP_K = 5

warnings.filterwarnings("ignore", category=DeprecationWarning)

# --- Device Setup ---
if torch.cuda.is_available():
    device = "cuda"
elif torch.backends.mps.is_available() and torch.backends.mps.is_built():
    device = "mps"
else:
    device = "cpu"
print(f"🔥 Using device: {device}")

# --- Embedding model ---
embedder = SentenceTransformer(EMBED_MODEL_NAME, device=device)

# --- Database & Vector clients ---
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
qdrant_client = QdrantClient(url=QDRANT_URL)

# --- Start Ollama server ---
ollama_process = subprocess.Popen(
    ["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    ["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
def shutdown_ollama():
    if os.name == 'nt':
        ollama_process.terminate()
    else:
        os.killpg(os.getpgid(ollama_process.pid), signal.SIGTERM)
    print("🚓 Ollama server stopped.")
atexit.register(shutdown_ollama)

# --- LightRAG QA Component ---
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

# --- FastAPI App ---
app = FastAPI()
class Question(BaseModel):
    query: str

# --- API Endpoints ---
@app.post("/ask")
def ask(data: Question):
    start = time.time()
    result = qa_pipeline.call(data.query)
    duration = round(time.time() - start, 2)
    return {
        "question": data.query,
        "answer": result.explanation,
        "example": result.example,
        "duration_seconds": duration,
    }


@app.get("/metadata")
def metadata():
    commit = subprocess.getoutput("git rev-parse HEAD")
    return {
        "embedding_model": EMBED_MODEL_NAME,
        "llm_model": OLLAMA_MODEL,
        "git_commit": commit,
        "device": device,
        "triplet_embeddings": True,
        "retriever": "LightRAG QA Component"
    }


# --- Run ---
if __name__ == "__main__":
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=False)
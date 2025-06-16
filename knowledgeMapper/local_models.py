# File: knowledgeMapper/local_models.py
# WORKAROUND version: Added translation methods to handle the "Denglisch" KG.

from __future__ import annotations
import asyncio
import requests
import torch
from sentence_transformers import CrossEncoder
from langchain.embeddings import HuggingFaceEmbeddings
from typing import TypedDict, List, Any


# --- Document Structure for Type Hinting ---
class Document(TypedDict):
    text: str
    metadata: dict


# --- Configuration ---
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
RERANKER_MODEL_NAME = "BAAI/bge-reranker-base" # This might be used internally by LightRAG
OLLAMA_MODEL_NAME = "llama3:8b"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
OLLAMA_HOST = "http://localhost:11434"

# --- Device Config ---
EMBEDDING_DEVICE_CONFIG = DEVICE
RERANKER_DEVICE_CONFIG = "cpu"

# --- Global State for Models ---
MODELS = {}
_EMBED_SEMAPHORE = asyncio.Semaphore(1)


# --- Model Classes (The Logic) ---

class AsyncEmbedder:
    def __init__(self):
        print(f"Loading embedding model '{EMBEDDING_MODEL_NAME}' onto device '{EMBEDDING_DEVICE_CONFIG}'...")
        self.hf = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL_NAME,
            encode_kwargs={"normalize_embeddings": True},
            model_kwargs={"device": EMBEDDING_DEVICE_CONFIG},
        )
        self.embedding_dim = self.hf.client.get_sentence_embedding_dimension()
        print("Embedding model loaded.")


    async def __call__(self, texts: list[str]) -> list[list[float]]:
        async with _EMBED_SEMAPHORE:
            return await asyncio.to_thread(self.hf.embed_documents, texts)


class Reranker:
    def __init__(self):
        print(f"Loading reranker model '{RERANKER_MODEL_NAME}' onto device '{RERANKER_DEVICE_CONFIG}'...")
        self.model = CrossEncoder(RERANKER_MODEL_NAME, max_length=512, device=RERANKER_DEVICE_CONFIG)
        print("Reranker model loaded.")

    def __call__(self, query: str, documents: List[Any]) -> List[Any]:
        if not documents:
            return []
        pairs = [(query, doc.text) for doc in documents]
        scores = self.model.predict(pairs, show_progress_bar=False)
        scored_docs = list(zip(scores.tolist(), documents))
        scored_docs.sort(key=lambda x: x[0], reverse=True)
        return [doc for score, doc in scored_docs]


class OllamaLLM:
    """ A wrapper for Ollama with added translation methods for the workaround. """

    async def _ollama_chat_call(self, messages: List[dict], temperature: float = 0.1) -> str:
        """ Private helper to make calls to the Ollama API. """
        def _call() -> str:
            r = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": OLLAMA_MODEL_NAME,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": temperature},
                },
                timeout=60_000,
            )
            r.raise_for_status()
            response_data = r.json()
            return response_data.get("message", {}).get("content", "")

        return await asyncio.to_thread(_call)

    async def translate_to_english(self, text: str) -> str:
        """ Translates a given German text to English. """
        system_prompt = "You are an expert translator. Translate the following German text to English. Output only the translated text, without any additional comments, preambles, or explanations."
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ]
        return await self._ollama_chat_call(messages, temperature=0.0)

    async def translate_to_german(self, text: str) -> str:
        """ Translates a given English text to German. """
        system_prompt = "You are an expert translator. Translate the following English text to German. Ensure the translation is natural and fluent. Output only the translated text, without any additional comments, preambles, or explanations."
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ]
        return await self._ollama_chat_call(messages, temperature=0.0)

    async def __call__(self, context: str = None, question: str = None, system_prompt: str = None, **kwargs) -> str:
        """
        The main __call__ method, compatible with LightRAG's internal operations.
        """
        prompt_content = context or kwargs.get('prompt')
        temperature = 0.1

        # Pattern 1: Internal keyword extraction call from LightRAG.
        if prompt_content and ("---Goal---" in prompt_content and "---Examples---" in prompt_content):
            print("   - (Info) Handling internal LightRAG keyword extraction call.")
            system_prompt_for_keywords = "You are an assistant that extracts keywords. Your only task is to follow the user's instructions exactly and provide the output in the JSON format shown in the examples. Do not provide any additional explanation, clarification, or introductory sentences. Your entire response must be only the JSON code."
            messages = [
                {"role": "system", "content": system_prompt_for_keywords},
                {"role": "user", "content": prompt_content}
            ]
            temperature = 0.0

        # Pattern 2: Standard RAG call for final answer generation (called by `aquery` with a custom prompt).
        else:
            print("   - (Info) Handling final answer generation call.")
            final_generation_prompt = prompt_content
            if not final_generation_prompt:
                raise ValueError("Received a generation call with no content.")

            # The system prompt is now passed in directly from api_server.py via `user_prompt`
            final_system_prompt = "You are a helpful AI assistant." # Generic fallback
            if system_prompt:
                final_system_prompt = system_prompt

            messages = [
                {"role": "system", "content": final_system_prompt},
                {"role": "user", "content": final_generation_prompt}
            ]

        return await self._ollama_chat_call(messages, temperature=temperature)

# --- Initializer and Getter Functions ---
def load_models():
    """Initializes all models and stores them in the global state."""
    print("Initializing embedding, reranker, and LLM wrappers...")
    MODELS["embedder"] = AsyncEmbedder()
    MODELS["reranker"] = Reranker()
    MODELS["llm"] = OllamaLLM()
    print("✅ All models initialized.")

def get_embedder() -> AsyncEmbedder:
    return MODELS["embedder"]

def get_reranker() -> Reranker:
    return MODELS["reranker"]

def get_llm() -> OllamaLLM:
    return MODELS["llm"]

# Legacy aliases for LightRAG initialization
def HFEmbedFunc():
    return get_embedder()

def OllamaLLM_Func():
    return get_llm()

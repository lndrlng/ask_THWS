# 🤖 Hybrid RAG Chatbot Architecture

This chatbot combines **semantic understanding** of raw crawled documents with **symbolic reasoning** over a structured knowledge graph built from triplets.

---

## 🔄 System Overview

```text
         ┌────────────────────────────┐
         │      User Input (Chat)     │
         └────────────┬───────────────┘
                      │
         ┌────────────▼─────────────┐
         │  Intent / Query Analysis │
         └────────────┬─────────────┘
                      │
        ┌─────────────▼────────────────────────────────────┐
        │        1. Semantic Retriever (Vector DB)          │
        │  🔍 Retrieves raw content from crawled data       │
        │  ✅ Uses link metadata and content embeddings     │
        └─────────────┬────────────────────────────────────┘
                      │
        ┌─────────────▼────────────────────────────────────┐
        │        2. Graph Reasoner (Neo4j + Cypher)         │
        │  🧠 Uses entity types & relations for symbolic     │
        │     lookup (e.g. Studiengang → Module)            │
        └─────────────┬────────────────────────────────────┘
                      │
              ┌───────▼────────┐
              │ Merge Contexts │ ← Combine vector + graph results
              └───────┬────────┘
                      │
        ┌─────────────▼────────────────────────────────────┐
        │      RAG Prompt Composition & LLM Completion      │
        │  ✨ Creates enriched prompts for factual & creative│
        │     responses from both sides of the pipeline     │
        └─────────────┬────────────────────────────────────┘
                      │
               ┌──────▼───────┐
               │   Response   │
               └──────────────┘
```
# 🔍 Hybrid RAG Pipeline for Crawled Data + Neo4j Knowledge Graph

This project processes raw crawled web content into a structured Knowledge Graph (Neo4j) and combines it with semantic search to power a hybrid Retrieval-Augmented Generation (RAG) chatbot.

---

## 🚀 Pipeline Overview

### 1. 🧹 `filterChunks`
Cleans raw crawled HTML/text content:
- Removes unwanted boilerplate (cookie banners, navigation bars)
- Retains metadata (page title, links, source URL)
- Outputs clean, chunkable text blocks

---

### 2. 🧠 `extract_triplets`
Extracts meaningful relationships using a Language Model:
- Uses LLM to identify subject–relation–object triplets
- Includes coreference resolution and NER enrichment
- Optionally tags source chunk or link for traceability

---

### 3. 🧼 `normalize_triplets`
Cleans, deduplicates, and enriches triplets:
- Normalizes entity casing and structure
- Strips titles like `Prof.`, `Dr.`, etc.
- Applies fuzzy matching to merge near-duplicate entities
- Assigns semantic labels (`ORG`, `PROGRAM`, `TOPIC`, `PER`, etc.)

---

### 4. 🔍 (Optional) `filter_triplets`
Cleans out noisy or low-confidence triplets:
- Filters generic references like “this”, “he”, “info”
- Optionally uses LLM confidence or hand-tuned rules

---

### 5. 🧩 `graphToNeo4j`
Builds a semantic Knowledge Graph:
- Loads normalized triplets into Neo4j
- Uses dynamic node labels based on entity type
- Supports custom Cypher queries and RAG subgraph retrieval

---

### 6. 🧠 Semantic Indexing (optional Hybrid RAG)
- Chunks raw text semantically
- Generates vector embeddings for retrieval
- Links each chunk to related nodes in the graph
- Enables combination of vector + symbolic search

---

## 💡 Use Cases

- "Which modules are included in the Studiengang Logistik?"
- "List all Personen mentioned in the Studientext with roles."
- "Write an introduction paragraph about the Twin-Zertifikat."
- "What’s the structure of the Kunststofftechnik program?"

---

## 🧱 Stack

| Layer              | Tech                      |
|-------------------|---------------------------|
| Data Processing    | Python, spaCy, Regex       |
| Triplet Extraction | LLM (OpenAI / Local)       |
| Entity Typing      | Rule-based + NER hybrid    |
| Graph DB           | Neo4j                      |
| Vector Search      | FAISS / Weaviate (optional)|
| LLM Backend        | GPT-4 / Claude / Mixtral   |
| RAG Framework      | LangChain / Custom          |

---

## 🗂️ Output Format

Each normalized triplet looks like:

```json
{
  "subject": "Twin-Programm",
  "subject_type": "PROGRAM",
  "relation": "vermittelt",
  "object": "Fachliche Kompetenzen",
  "object_type": "TOPIC"
}

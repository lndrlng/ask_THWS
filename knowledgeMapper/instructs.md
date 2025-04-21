
# Install requirements
```text
pip install numpy==3.5 
pip install spacy==3.5.4 
pip install coreferee==1.4.1
pip install de-core-news-md==3.5.0
pip install neo4j
pip install python-Levenshtein
pip install fuzzywuzzy[levenshtein]
```
## Start Visulator
   streamlit run visualize_triplets_app.py
## Neo4J setup using docker

### may change user and pw
```text
User = neo4j
PW = kg123lol!1
```
```text
docker run -d --name neo4j-kg -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/kg123lol!1 neo4j:5
```

### 🛠️ Current Data Processing Pipeline

1. **filterChunks**  
   Remove unwanted content like cookie banners, navigation bars, etc.

2. **extract_triplets**  
   Use an LLM to extract subject–relation–object triplets from text.  
   Includes utilities like coreference resolution and NER enrichment for more reliable extractions.

3. **normalize_triplets**  
   Normalize text, deduplicate similar entities, and assign dynamic labels (`ORG`, `TOPIC`, `PROGRAM`, etc.).

4. **graphToNeo4j**  
   Load triplets into Neo4j to build a structured and queryable Knowledge Graph.

### 🚀 Future Improvements

1. **Improve Triplet Quality**
   - Add confidence scoring to filter hallucinated or weak triplets
   - Chunk text by semantic units for cleaner, more meaningful extraction

2. **Enhance Graph Semantics**
   - Add entity descriptions to nodes (e.g. what is a Studiengang?)
   - Use fine-grained Neo4j labels by entity type (`:ORG`, `:TOPIC`, `:PROGRAM`, etc.)

3. **Linkage & Traceability**
   - Auto-link triplets to their source documents (`chunk_id`, `URL`)
   - Add document/source metadata to triplets for answer traceability

4. **RAG Improvements**
   - HybridRetriever implementation (combine vector + graph results)
   - Use Graph-based summarization (generate answers from subgraphs)
   - LangChain CypherChain integration for symbolic question answering

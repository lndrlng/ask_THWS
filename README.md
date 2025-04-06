# RAG THWS Tool

# Parts
1. webscraper
2. Text Preprocessing & Chunking
    - cleanup text
    - make chunks fitting the context window of the llm
    - overlapping 1 sentence, so the model gets the context
3. Vector storage
    - with an embedding modell
    - Qdrant as db
        - fast (in rust)
        - allows metadata
        - python library
4. Frontend
    - 

---

# Running the stuff

# Setup

open the rag repository Folder in Terminal and install the python dependencies

```shell
pip install -r requirements.txt
```

# How to run the scraper

```shell
cd thws_scraper
scrapy crawl thws -o ../data/thws_data_raw.json
```

# Preprocess the data
```shell
python3 preprocess_and_chunk.py data/thws_data_raw.json
```

# Load to Vector db
```shell
docker compose up -d
python3 embed_to_qdrant.py data/thws_data_chunks.json
```

# Running
```shell
ollama serve
python3 query.py
```
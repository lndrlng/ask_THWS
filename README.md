# RAG THWS Tool

# Parts

1. webscraper

   - **Disallow: /fileadmin/**: A lot of PDFs are skipped through this rule. Should we skip this rule, or do we need approval from the university?

1. Text Preprocessing & Chunking

   - cleanup text
   - make chunks fitting the context window of the llm
   - overlapping 1 sentence, so the model gets the context

1. Vector storage

   - with an embedding modell
   - Qdrant as db
     - fast (in rust)
     - allows metadata
     - python library

1. Frontend

## Ideas

- **Webapp for manual model comparison**

  Build a web interface that shows each question and its reference answer alongside anonymized model outputs (labeled A, B, C, …). Evaluators rank the blind responses by quality, producing unbiased, user-driven performance metrics.

- **Containerized scraper with DB backend**

  Package your crawler in Docker and connect it to a persistent database (e.g. PostgreSQL or MongoDB). Persist raw content, metadata and “seen URL” state to enable fast, incremental re-scrapes; ensure identical environments across dev, staging and production. Add Scrapy addon scrapy-deltafetch. It skips already-seen pages based on saved fingerprints, reducing redundant downloads

______________________________________________________________________

# Running the stuff

# Setup

To setup python follow [this steps](https://dav354.github.io/askTHWS/dev-tools/python/).

Then you need to set up the git [pre-commit hooks](https://dav354.github.io/askTHWS/dev-tools/precommit/) to ensure that we use all the same formatting of the files.

Open the rag repository Folder in Terminal and install the python dependencies

```shell
pip install -r requirements.txt
```

# How to run the scraper

```shell
cd thws_scraper && scrapy crawl thws
```

This will output the raw data and the chunked data in the thws_scraper folder.

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

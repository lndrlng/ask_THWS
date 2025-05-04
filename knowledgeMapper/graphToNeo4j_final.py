import json
import logging
import os
from tqdm import tqdm
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer
import torch
import os
import sys

# ------------------ Config ------------------
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "kg123lol!1"
TRIPLET_FILE = "./../data/studiengaenge_triplets.json"
PRIMARY_MODEL = "BAAI/bge-m3"
FALLBACK_MODEL = "all-MiniLM-L6-v2"

# ------------------ Setup ------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

device = "cuda" if torch.cuda.is_available() else "cpu"
embedder = None

def load_embedder(model_name: str):
    try:
        logging.info(f"🔍 Loading embedding model: {model_name}")
        return SentenceTransformer(model_name, device=device)
    except Exception as e:
        logging.warning(f"⚠️ Failed to load model '{model_name}': {e}")
        return None

# Disable symlink warning if necessary
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

embedder = load_embedder(PRIMARY_MODEL)
if embedder is None:
    logging.warning(f"⛔ Falling back to safer model: {FALLBACK_MODEL}")
    embedder = load_embedder(FALLBACK_MODEL)

if embedder is None:
    logging.critical("❌ Could not load any embedding model. Exiting.")
    sys.exit(1)

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# ------------------ Schema Setup ------------------
def create_constraints(tx):
    tx.run("CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE")

def create_fulltext_index(tx):
    tx.run("""
        CREATE FULLTEXT INDEX entityIndex IF NOT EXISTS
        FOR (n:PER|ORG|PROGRAM) ON EACH [n.name]
    """)


# ------------------ Triplet Insertion ------------------
def add_triplet(tx, subj, subj_type, rel, obj, obj_type, confidence, origin, metadata):
    date_updated = metadata.get("date_updated") or ""
    query = f"""
        MERGE (a:{subj_type} {{name: $subj}})
        MERGE (b:{obj_type} {{name: $obj}})
        MERGE (a)-[r:`{rel}` {{
            confidence: $confidence,
            origin: $origin,
            title: $title,
            source: $source,
            doc_type: $doc_type,
            lang: $lang,
            date_updated: $date_updated
        }}]->(b)
    """
    tx.run(query,
           subj=subj, obj=obj, confidence=confidence, origin=origin,
           title=metadata.get("title", ""),
           source=metadata.get("source", ""),
           doc_type=metadata.get("type", ""),
           lang=metadata.get("lang", ""),
           date_updated=date_updated)

# ------------------ Embedding Node Names ------------------
def embed_and_store_nodes():
    with driver.session() as session:
        result = session.run("""
            MATCH (n)
            WHERE n.name IS NOT NULL AND n.embedding IS NULL
                AND any(lbl IN labels(n) WHERE lbl IN ['PER', 'ORG', 'PROGRAM'])
            RETURN id(n) AS id, n.name AS name
        """)

        records = list(result)
        logging.info(f"🧠 Embedding {len(records)} new graph nodes...")

        for record in tqdm(records, desc="Embedding nodes"):
            node_id = record["id"]
            name = record["name"]
            try:
                embedding = embedder.encode(name, device=device).tolist()
                session.run("""
                    MATCH (n) WHERE id(n) = $id
                    SET n.embedding = $embedding
                """, id=node_id, embedding=embedding)
            except Exception as e:
                logging.warning(f"❌ Failed to embed '{name}': {e}")

# ------------------ Main ------------------
if __name__ == "__main__":
    with driver.session() as session:
        session.execute_write(create_constraints)
        session.execute_write(create_fulltext_index)

with open("./../data/studiengaenge_triplets_converted.json", "r", encoding="utf-8") as f:
    triplets = json.load(f)

logging.info(f"Loaded {len(triplets)} labeled triplets for Neo4j upload.")

with driver.session() as session:
    success_count = 0
    failure_count = 0
    for triplet in tqdm(triplets, desc="Uploading to Neo4j", unit="triplet"):
        # Normalize list-structured triplets to dict form
        if isinstance(triplet, list) and len(triplet) == 3:
            triplet = {
                "subject": triplet[0],
                "relation": triplet[1],
                "object": triplet[2],
                "subject_type": "Entity",
                "object_type": "Entity",
                "confidence": 1.0,
                "origin": "llm",
                "source_metadata": {}
            }
        try:
            session.execute_write(
                add_triplet,
                triplet["subject"],
                triplet.get("subject_type", "Entity"),
                triplet["relation"],
                triplet["object"],
                triplet.get("object_type", "Entity"),
                triplet.get("confidence", 1.0),
                triplet.get("origin", "llm"),
                triplet.get("source_metadata", {})
            )
            success_count += 1
        except Exception as e:
            logging.warning(f"❌ Failed to insert triplet: {triplet} — {e}")
            failure_count += 1

logging.info(f"✅ Finished uploading {success_count}/{len(triplets)} triplets successfully, {failure_count} failed.")

import json
import logging
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
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def load_embedder(model_name: str):
    try:
        logging.info(f"🔍 Loading embedding model: {model_name}")
        return SentenceTransformer(model_name, device=device)
    except Exception as e:
        logging.warning(f"⚠️ Failed to load model '{model_name}': {e}")
        return None

embedder = load_embedder(PRIMARY_MODEL) or load_embedder(FALLBACK_MODEL)
if embedder is None:
    logging.critical("❌ Could not load any embedding model. Exiting.")
    sys.exit(1)

# ------------------ Schema Setup ------------------
def create_constraints(tx):
    tx.run("CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE")

def create_fulltext_index(tx):
    tx.run("""
        CREATE FULLTEXT INDEX entityIndex IF NOT EXISTS
        FOR (n:PER|ORG|PROGRAM) ON EACH [n.name]
    """)

def create_vector_index(tx):
    labels = ["PER", "ORG", "PROGRAM"]
    for label in labels:
        tx.run(f"""
            CREATE VECTOR INDEX entityEmbeddingIndex_{label} IF NOT EXISTS
            FOR (n:{label}) ON (n.embedding)
            OPTIONS {{
                indexConfig: {{
                    `vector.dimensions`: 1024,
                    `vector.similarity_function`: 'cosine'
                }}
            }}
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
            RETURN elementId(n) AS eid, n.name AS name
        """)
        records = list(result)
        total = len(records)
        logging.info(f"🧠 Embedding {total} new graph nodes...")

        with tqdm(total=total, desc="Embedding nodes", unit="node", dynamic_ncols=True) as pbar:
            for record in records:
                eid = record["eid"]
                name = record["name"]
                try:
                    embedding = embedder.encode(name, device=device).tolist()
                    session.run("""
                        MATCH (n) WHERE elementId(n) = $eid
                        SET n.embedding = $embedding
                    """, eid=eid, embedding=embedding)
                except Exception as e:
                    logging.warning(f"❌ Failed to embed '{name}': {e}")
                pbar.update(1)

# ------------------ Embedding Triplet Relations ------------------
def embed_and_store_triplets():
    with driver.session() as session:
        result = session.run("""
            MATCH (a)-[r]->(b)
            WHERE r.triplet_embedding IS NULL AND a.name IS NOT NULL AND b.name IS NOT NULL
            RETURN elementId(r) AS rid, a.name AS subj, type(r) AS rel, b.name AS obj
        """)
        records = list(result)
        logging.info(f"🔗 Embedding {len(records)} relationships as triplets...")

        for record in tqdm(records, desc="Embedding triplets", leave=False):
            rid = record["rid"]
            triplet_str = f"{record['subj']} {record['rel']} {record['obj']}"
            try:
                embedding = embedder.encode(triplet_str, device=device).tolist()
                session.run("""
                    MATCH ()-[r]->() WHERE elementId(r) = $rid
                    SET r.triplet_embedding = $embedding
                """, rid=rid, embedding=embedding)
            except Exception as e:
                logging.warning(f"❌ Failed to embed triplet '{triplet_str}': {e}")

# ------------------ Main ------------------
if __name__ == "__main__":
    with driver.session() as session:
        session.execute_write(create_constraints)
        session.execute_write(create_fulltext_index)
        session.execute_write(create_vector_index)

    # Load triplets
    with open(TRIPLET_FILE, "r", encoding="utf-8") as f:
        triplets = json.load(f)
    logging.info(f"📦 Loaded {len(triplets)} triplets for import.")

    with driver.session() as session:
        for triplet in tqdm(triplets, desc="Uploading to Neo4j", unit="triplet", leave=False):
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
            except Exception as e:
                logging.warning(f"❌ Failed to insert triplet: {triplet} — {e}")

    logging.info(f"✅ Finished uploading triplets.")
    embed_and_store_nodes()
    embed_and_store_triplets()
    logging.info("✅ All embeddings complete.")

import json
import logging
from tqdm import tqdm
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer
import torch

# ------------------ Config ------------------
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "kg123lol!1"
TRIPLET_FILE = "./../data/studiengaenge_triplets.json"
EMBED_MODEL_NAME = "BAAI/bge-m3"  # Update this if using another model

# ------------------ Setup ------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

device = "cuda" if torch.cuda.is_available() else "cpu"
embedder = SentenceTransformer(EMBED_MODEL_NAME, device=device)
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# ------------------ Schema Setup ------------------
def create_constraints(tx):
    tx.run("CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE")

def create_fulltext_index(tx):
    tx.run("""
        CALL db.index.fulltext.createNodeIndex(
            "entityIndex", 
            ["PER", "ORG", "PROGRAM"], 
            ["name"]
        )
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
            WHERE n.name IS NOT NULL AND NOT exists(n.embedding)
              AND any(lbl IN labels(n) WHERE lbl IN ['PER', 'ORG', 'PROGRAM'])
            RETURN id(n) AS id, n.name AS name
        """)
        records = list(result)
        logging.info(f"🧠 Embedding {len(records)} new graph nodes...")

        for record in tqdm(records, desc="Embedding nodes"):
            node_id = record["id"]
            name = record["name"]
            embedding = embedder.encode(name, device=device).tolist()

            session.run("""
                MATCH (n) WHERE id(n) = $id
                SET n.embedding = $embedding
            """, id=node_id, embedding=embedding)

# ------------------ Main ------------------
if __name__ == "__main__":
    with driver.session() as session:
        session.execute_write(create_constraints)
        session.execute_write(create_fulltext_index)

    # Load triplets
    with open(TRIPLET_FILE, "r", encoding="utf-8") as f:
        triplets = json.load(f)
    logging.info(f"📦 Loaded {len(triplets)} triplets for import.")

    with driver.session() as session:
        for triplet in tqdm(triplets, desc="Uploading to Neo4j", unit="triplet"):
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

    # Add embeddings
    embed_and_store_nodes()
    logging.info("✅ All relevant nodes have been embedded.")

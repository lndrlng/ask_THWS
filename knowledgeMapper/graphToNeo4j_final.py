
import json
import logging
from tqdm import tqdm
from neo4j import GraphDatabase

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Neo4j connection
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "kg123lol!1"

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# Constraint setup
def create_constraints(tx):
    tx.run("CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE")

# Triplet insertion with confidence and origin
def add_triplet(tx, subj, subj_type, rel, obj, obj_type, confidence, origin, metadata):
    tx.run(f"""
        MERGE (a:{subj_type} {{name: $subj}})
        MERGE (b:{obj_type} {{name: $obj}})
        MERGE (a)-[r:RELATION {{
            type: $rel,
            confidence: $confidence,
            origin: $origin,
            title: $title,
            source: $source,
            doc_type: $doc_type,
            lang: $lang,
            date_updated: $date_updated
        }}]->(b)
    """, subj=subj, obj=obj, rel=rel, confidence=confidence, origin=origin,
        title=metadata.get("title", ""),
        source=metadata.get("source", ""),
        doc_type=metadata.get("type", ""),
        lang=metadata.get("lang", ""),
        date_updated=metadata.get("date_updated", "")
    )

with driver.session() as session:
    session.execute_write(create_constraints)

with open("./../data/KgData/Triplets_labeled_final.json", "r", encoding="utf-8") as f:
    triplets = json.load(f)

logging.info(f"Loaded {len(triplets)} labeled triplets for Neo4j upload.")

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

logging.info(f"✅ Finished uploading {len(triplets)} triplets to Neo4j.")

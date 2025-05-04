import json
import logging
import os
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

# Triplet insertion with dynamic relationship type
def add_triplet(tx, subj, subj_type, rel, obj, obj_type, confidence, origin, metadata):
    date_updated = metadata.get("date_updated")
    if date_updated is None:
        date_updated = ""
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
           date_updated=date_updated
           )

with driver.session() as session:
    session.execute_write(create_constraints)

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

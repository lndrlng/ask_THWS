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

# Constraint setup (one-time, generic backup)
def create_constraints(tx):
    tx.run("CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE")

# Smart node insert with dynamic labels
def add_triplet(tx, subj, subj_type, rel, obj, obj_type):
    tx.run(f"""
        MERGE (a:{subj_type} {{name: $subj}})
        MERGE (b:{obj_type} {{name: $obj}})
        MERGE (a)-[r:RELATION {{type: $rel}}]->(b)
    """, subj=subj, obj=obj, rel=rel)

# Run constraint
with driver.session() as session:
    session.execute_write(create_constraints)

# Load processed + labeled triplets
with open("../../data/KgData/Triplets_labeled_final.json", "r", encoding="utf-8") as f:
    triplets = json.load(f)

logging.info(f"Loaded {len(triplets)} labeled triplets for Neo4j upload.")

# Upload to Neo4j
with driver.session() as session:
    for triplet in tqdm(triplets, desc="Uploading to Neo4j", unit="triplet"):
        try:
            session.execute_write(
                add_triplet,
                triplet["subject"],
                triplet["subject_type"],
                triplet["relation"],
                triplet["object"],
                triplet["object_type"]
            )
        except Exception as e:
            logging.warning(f"❌ Failed to insert triplet: {triplet} — {e}")

logging.info(f"✅ Finished uploading {len(triplets)} triplets to Neo4j.")

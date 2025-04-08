import json
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "your_password_here"

# Connect to Neo4j
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def add_triplet(tx, subj, rel, obj):
    tx.run("""
    MERGE (a:Entity {name: $subj})
    MERGE (b:Entity {name: $obj})
    MERGE (a)-[:RELATION {type: $rel}]->(b)
    """, subj=subj, obj=obj, rel=rel)

# Load extracted triplets
with open(" ./../data/triplets.json", "r", encoding="utf-8") as f:
    triplets = json.load(f)

# Insert into Neo4j
with driver.session() as session:
    for triplet in triplets:
        try:
            parsed = triplet.strip("() ").split(",")
            if len(parsed) == 3:
                subj, rel, obj = map(str.strip, parsed)
                session.write_transaction(add_triplet, subj, rel, obj)
        except Exception as e:
            print(f"Error with triplet {triplet}: {e}")

print(f"✅ Uploaded {len(triplets)} triplets to Neo4j.")
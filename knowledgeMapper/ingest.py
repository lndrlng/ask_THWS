# File: knowledgeMapper/migrate_to_neo4j.py
# Description: v2.1 - Adds a crucial step to create a database index/constraint,
# which is necessary for LightRAG to find nodes efficiently.

import os
import asyncio
import json
import networkx as nx
from neo4j import AsyncGraphDatabase
from typing import Dict, Any, List

# ==============================================================================
# CONFIGURATION
# ==============================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
RAG_STORAGE_DIR = os.path.join(PROJECT_ROOT, "rag_storage")

GRAPHML_FILE = os.path.join(RAG_STORAGE_DIR, "graph_chunk_entity_relation.graphml")
ENTITIES_FILE = os.path.join(RAG_STORAGE_DIR, "vdb_entities.json")
RELATIONSHIPS_FILE = os.path.join(RAG_STORAGE_DIR, "vdb_relationships.json")

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "kg123lol!1" # <-- IMPORTANT: SET YOUR PASSWORD HERE
# ==============================================================================

def load_json_data(file_path: str) -> List[Dict[str, Any]]:
    """Loads a JSON file and returns its 'data' key, which is expected to be a list."""
    if not os.path.exists(file_path):
        print(f"ERROR: Data file not found: {file_path}")
        return []
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f).get("data", [])
        if not isinstance(data, list):
            print(f"WARNING: Expected 'data' in {file_path} to be a list, but got {type(data)}.")
            return []
        return data

async def batch_migrate(session, query, data_list, batch_size=1000):
    """Runs a batched Cypher query using UNWIND."""
    total = len(data_list)
    for i in range(0, total, batch_size):
        batch = data_list[i:i + batch_size]
        await session.run(query, data=batch)
        print(f"  - Processed batch {i//batch_size + 1}/{(total + batch_size - 1)//batch_size}...")

async def migrate_data():
    """Connects to Neo4j, creates necessary indexes, and writes the data in batches."""
    print("Starting lightweight migration process from local files to Neo4j...")

    # 1. Load all source data from files
    print(f"Loading graph structure from {GRAPHML_FILE}...")
    if not os.path.exists(GRAPHML_FILE):
        print(f"ERROR: GraphML file not found: {GRAPHML_FILE}")
        return
    G = nx.read_graphml(GRAPHML_FILE)
    print(f"  - Loaded a graph with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")

    print(f"Loading entity metadata from {ENTITIES_FILE}...")
    entities_data = load_json_data(ENTITIES_FILE)
    entities_lookup = {item.get('entity_name'): item for item in entities_data}

    print(f"Loading relationship metadata from {RELATIONSHIPS_FILE}...")
    relationships_data = load_json_data(RELATIONSHIPS_FILE)
    relationships_lookup = {(item.get('src_id'), item.get('tgt_id')): item for item in relationships_data}

    # 2. Connect to Neo4j
    driver = None
    try:
        driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
        await driver.verify_connectivity()
        print("\nSuccessfully connected to Neo4j.")

        async with driver.session() as session:
            # Optional: Clear the database before migrating
            # print("Clearing existing data from Neo4j...")
            # await session.run("MATCH (n) DETACH DELETE n")

            # NEW: Create a unique constraint and index on the 'name' property of 'Entity' nodes.
            # This is CRUCIAL for performance and for LightRAG to find nodes.
            print("\nEnsuring database index/constraint exists...")
            index_query = "CREATE CONSTRAINT entity_name_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE"
            await session.run(index_query)
            print("  - Index/Constraint on :Entity(name) is ready.")

            # 3. Prepare and batch-migrate nodes
            print(f"\nPreparing {G.number_of_nodes()} nodes for migration...")
            node_list = []
            for node_id, node_attrs in G.nodes(data=True):
                entity_props = entities_lookup.get(node_id, {})
                final_props = {
                    "name": node_id, "entity_type": node_attrs.get("entity_type"),
                    "description": node_attrs.get("description"), "source_id": node_attrs.get("source_id"),
                    "embedding": entity_props.get("vector"), "content": entity_props.get("content")
                }
                node_list.append({k: v for k, v in final_props.items() if v is not None})

            node_query = "UNWIND $data as props MERGE (e:Entity {name: props.name}) SET e += props"
            await batch_migrate(session, node_query, node_list)
            print(f"  - Node migration complete.")

            # 4. Prepare and batch-migrate edges
            print(f"\nPreparing {G.number_of_edges()} relationships for migration...")
            edge_list = []
            for u, v, edge_attrs in G.edges(data=True):
                rel_props = relationships_lookup.get((u, v)) or relationships_lookup.get((v, u), {})
                final_props = {
                    "description": edge_attrs.get("description"), "keywords": edge_attrs.get("keywords"),
                    "weight": edge_attrs.get("weight"), "source_id": edge_attrs.get("source_id"),
                    "embedding": rel_props.get("vector")
                }
                edge_list.append({
                    "source_name": u, "target_name": v,
                    "props": {k: v for k, v in final_props.items() if v is not None}
                })

            edge_query = """
            UNWIND $data as edge
            MATCH (a:Entity {name: edge.source_name})
            MATCH (b:Entity {name: edge.target_name})
            MERGE (a)-[r:RELATES]->(b)
            SET r = edge.props
            """
            await batch_migrate(session, edge_query, edge_list)
            print(f"  - Relationship migration complete.")

        print("\n✅ Migration complete!")

    except Exception as e:
        print(f"\n❌ An error occurred during migration: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if driver:
            await driver.close()

if __name__ == "__main__":
    print("This script migrates existing LightRAG file storage to Neo4j.")
    print("Prerequisites: `pip install neo4j networkx`")
    print("NOTE: Ensure your Neo4j database is running before starting.")
    asyncio.run(migrate_data())

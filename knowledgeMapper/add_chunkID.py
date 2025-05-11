import json

INPUT_FILE = "../data/lightrag/fiw_results.json"
OUTPUT_FILE = "./../data/fiw_results_with_ids.json"  # You can overwrite input file if you want

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_chunk_ids(data):
    for i, chunk in enumerate(data):
        chunk["chunk_id"] = f"chunk_{i}"
    return data

if __name__ == "__main__":
    print("📂 Loading data...")
    chunks = load_json(INPUT_FILE)

    print("🔧 Adding chunk_id to each chunk...")
    updated_chunks = add_chunk_ids(chunks)

    print("💾 Saving to output file...")
    save_json(updated_chunks, OUTPUT_FILE)

    print(f"✅ Done. Added chunk_id to {len(updated_chunks)} chunks.")

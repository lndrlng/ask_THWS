import json

# ❌ Junk indicators (UI, navigation, legal, social media)
BOILERPLATE_PHRASES = [
    "zum inhalt wechseln", "zum hauptmenü wechseln", "zur suche wechseln",
    "zur sprachauswahl wechseln", "zur servicenavigation wechseln"
]

# ✅ Relevant topic keywords (whitelist if needed)
IMPORTANT_KEYWORDS = [
    "professor", "forschungsprojekt", "preis", "stipendium", "fachbereich",
    "veranstaltung", "hackathon", "studiengang", "master", "kooperation",
    "projekt", "international", "forschung", "künstliche intelligenz", "partnerhochschule"
]

def is_chunk_valid(chunk):
    text = chunk.get("text", "").lower()

    # 🧹 Skip known boilerplate junk
    if any(bp in text for bp in BOILERPLATE_PHRASES):
        return False

    # ❌ Too short or repetitive
    words = text.split()
    if len(words) < 15:
        return False
    unique_ratio = len(set(words)) / max(len(words), 1)
    if unique_ratio < 0.25:
        return False

    # ✅ Bonus: keep if important topic detected
    if any(kw in text for kw in IMPORTANT_KEYWORDS):
        return True

    # ❌ Otherwise reject if it's too generic
    if "technische hochschule würzburg-schweinfurt" in text and "startseite" in text:
        return False

    return True

def filter_chunks(input_path, output_path):
    with open(input_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    filtered = [chunk for chunk in chunks if is_chunk_valid(chunk)]

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(filtered, f, indent=2, ensure_ascii=False)

    print(f"✅ Filtered {len(filtered)} / {len(chunks)} chunks saved to '{output_path}'")

# 🏁 Example usage
if __name__ == "__main__":
    input_file = "./../data/thws_data2_chunks.json"
    output_file = "./../data/thws_data_filtered.json"
    filter_chunks(input_file, output_file)

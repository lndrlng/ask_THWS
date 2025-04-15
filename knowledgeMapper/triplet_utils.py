import json
import os
import re
import spacy

# === Load spaCy German model ===
nlp = spacy.load("de_core_news_md")

# === DEBUG MODE ===
DEBUG = False

# === ENTITY NORMALIZATION ===
def normalize_entity(ent: str) -> str:
    ent = ent.strip()
    ent = re.sub(r"Prof(essor)?(\.?) Dr(\.?)?", "", ent, flags=re.IGNORECASE).strip()

    synonyms = {
        "USA": "USA",
        "U.S.": "USA",
        "United States": "USA",
        "Student:innen": "Studierende",
        "Studierenden": "Studierende",
        "Studenten": "Studierende",
        "Lernende": "Studierende",
        "COVID-19": "COVID-19-Pandemie",
        "Corona": "COVID-19-Pandemie",
        "Kliniker*innen": "Kliniker",
        "Ärzt*innen": "Ärztinnen und Ärzte",
        "Gesundheitsdienstleister*innen": "Gesundheitspersonal",
        "Autorengruppe": "Forschungsgruppe",
        "Forscher*innengruppe": "Forschungsgruppe",
    }

    return synonyms.get(ent, ent)

# === TRIPLET VALIDATION ===
def is_valid_triplet(line: str) -> bool:
    return re.match(r"^\(.+?,.+?,.+?\)$", line)

# === TRIPLET PARSING ===
def parse_triplets(text: str):
    triplets = []
    # Find all segments that *look* like triplets inside the messy text
    matches = re.findall(r"\(([^()]+?,[^()]+?,[^()]+?)\)", text)

    for match in matches:
        try:
            subj, pred, obj = map(str.strip, match.split(",", 2))
            subj = normalize_entity(subj)
            obj = normalize_entity(obj)

            # Flag pronouns for postprocessing (optional enhancement)
            if subj.lower() in {"es", "er", "sie", "dies", "diese", "dieser", "they", "it", "he", "she"}:
                subj = "[RESOLVE_ME]"

            triplets.append((subj, pred, obj))
        except Exception:
            continue

    return triplets


# === NER ENRICHMENT ===
def enrich_with_ner(text: str):
    doc = nlp(text)
    filtered = set()

    for ent in doc.ents:
        ent_text = ent.text.strip()
        if 2 <= len(ent_text) <= 100:
            filtered.add(ent_text)

    return list(filtered)

# === FILE HELPERS ===
def load_json(path: str):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_json(data, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

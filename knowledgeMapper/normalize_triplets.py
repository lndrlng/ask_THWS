import json
import re
import spacy
import logging
from tqdm import tqdm
from pathlib import Path
from rapidfuzz import fuzz  # Faster fuzzy matching

# Setup
logging.basicConfig(level=logging.INFO)
nlp = spacy.load("de_core_news_md")

# Paths
input_path = Path("./../data/KgData/Triplets_finished.json")
output_path = Path("./../data/KgData/Triplets_labeled_final.json")  # fixed relative path

# Ensure output directory exists
output_path.parent.mkdir(parents=True, exist_ok=True)

# Load raw triplets
with input_path.open("r", encoding="utf-8") as f:
    raw_triplets = json.load(f)

# Load already processed (if exists)
if output_path.exists():
    with output_path.open("r", encoding="utf-8") as f:
        normalized_triplets = json.load(f)
    processed_set = set((t["subject"], t["relation"], t["object"]) for t in normalized_triplets)
    logging.info(f"Resuming: {len(normalized_triplets)} triplets already processed.")
else:
    normalized_triplets = []
    processed_set = set()
    logging.info("Starting fresh.")

# Deduplication cache
entity_cache = {}

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if isinstance(text, str) else text

def strip_titles(name):
    blacklist = {"prof.", "dr.", "herr", "frau"}
    tokens = name.lower().split()
    return " ".join(t for t in tokens if t not in blacklist).title()

def normalize_entity(entity):
    return strip_titles(clean_text(entity))

def deduplicate_entity(entity):
    norm = normalize_entity(entity)
    for known in entity_cache:
        if fuzz.ratio(norm.lower(), known.lower()) > 90:
            return entity_cache[known]
    entity_cache[norm] = norm
    return norm

def get_entity_type(entity):
    doc = nlp(entity)
    for ent in doc.ents:
        if ent.text.strip().lower() in entity.lower():
            return ent.label_
    return "Unknown"

def classify_entity(entity, spacy_label):
    text = entity.lower()
    if any(kw in text for kw in ["studiengang", "studiengänge", "twin-programm", "logistikstudium"]):
        return "PROGRAM"
    if any(kw in text for kw in ["bachelorarbeit", "praxissemester", "grundstudium", "hauptstudium", "vertiefungsstudium", "fachsemester", "modul"]):
        return "MODULE"
    if any(kw in text for kw in ["projektarbeit", "lehrinhalt", "thema", "inhalt", "kompetenz", "fach", "wissen"]):
        return "TOPIC"
    if any(kw in text for kw in ["labor", "ressource", "werkstatt", "geräte", "raum"]):
        return "RESOURCE"
    if any(kw in text for kw in ["fakultät", "hochschule", "universität", "schule", "institut", "organisation"]):
        return "ORG"
    if any(kw in text for kw in ["bayern", "mainfranken", "europa", "labor", "ort", "stadt"]):
        return "LOC"
    if any(kw in text for kw in ["kontakt", "telefon", "email"]):
        return "CONTACT"
    if any(kw in text for kw in ["zertifikat", "abschluss", "urkunde"]):
        return "CERT"
    if any(kw in text for kw in ["student", "dozent", "professor", "person", "leiter", "bewerber", "absolvent", "kille", "jonas", "marcus"]):
        return "PER"
    if spacy_label in {"PER", "ORG", "LOC", "MISC"}:
        return spacy_label
    return "MISC"

# Process with tqdm
new_entries = 0
for triplet in tqdm(raw_triplets, desc="Normalizing Triplets", unit="triplet"):
    if len(triplet) != 3:
        continue

    subj, rel, obj = triplet
    subj_norm = deduplicate_entity(subj)
    obj_norm = deduplicate_entity(obj)
    rel_norm = clean_text(rel.lower())

    triplet_key = (subj_norm, rel_norm, obj_norm)
    if triplet_key in processed_set:
        continue

    subj_label = get_entity_type(subj_norm)
    obj_label = get_entity_type(obj_norm)

    subj_type = classify_entity(subj_norm, subj_label)
    obj_type = classify_entity(obj_norm, obj_label)

    normalized_triplets.append({
        "subject": subj_norm,
        "subject_type": subj_type,
        "relation": rel_norm,
        "object": obj_norm,
        "object_type": obj_type
    })

    processed_set.add(triplet_key)
    new_entries += 1

    if new_entries % 1000 == 0:
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(normalized_triplets, f, ensure_ascii=False, indent=2)

# Final save
with output_path.open("w", encoding="utf-8") as f:
    json.dump(normalized_triplets, f, ensure_ascii=False, indent=2)

logging.info(f"✅ Finished. Total normalized triplets: {len(normalized_triplets)}")

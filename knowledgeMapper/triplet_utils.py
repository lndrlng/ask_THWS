# === triplet_utils.py (refined) ===
import json
import os
import re
import spacy
from rapidfuzz import fuzz

nlp = spacy.load("de_core_news_md")

# Cache for deduplication
entity_cache = {}

# === Cleaning ===
def clean_text(text):
    return re.sub(r"\s+", " ", text).strip() if isinstance(text, str) else ""

def strip_titles(name):
    blacklist = {"prof.", "dr.", "herr", "frau"}
    return " ".join(t for t in name.lower().split() if t not in blacklist).title()

def normalize_entity(entity):
    entity = clean_text(entity)
    entity = re.sub(r"Prof(essor)?(\\.?) Dr(\\.?)?", "", entity, flags=re.IGNORECASE).strip()
    synonyms = {
        "USA": "USA", "U.S.": "USA", "United States": "USA",
        "Student:innen": "Studierende", "Studierenden": "Studierende",
        "COVID-19": "COVID-19-Pandemie", "Corona": "COVID-19-Pandemie"
    }
    entity = synonyms.get(entity, strip_titles(entity))
    for known in entity_cache:
        if fuzz.ratio(entity.lower(), known.lower()) > 90:
            return entity_cache[known]
    entity_cache[entity] = entity
    return entity

# === Triplet Parsing ===
def is_valid_triplet(line):
    return re.match(r"^\(.+?,.+?,.+?\)$", line)

def parse_triplets(text):
    triplets = []
    matches = re.findall(r"\(([^()]+?,[^()]+?,[^()]+?)\)", text)
    for match in matches:
        try:
            subj, pred, obj = map(str.strip, match.split(",", 2))
            subj = normalize_entity(subj)
            obj = normalize_entity(obj)
            if len(subj.split()) > 12 or len(obj.split()) > 12:
                continue
            if subj.lower() in {"es", "er", "sie", "dies", "diese", "dieser", "they", "it", "he", "she"}:
                subj = "[RESOLVE_ME]"
            triplets.append((subj, pred, obj))
        except Exception:
            continue
    return triplets

# === NER Enrichment ===
def enrich_with_ner(text):
    doc = nlp(text)
    return list({normalize_entity(ent.text.strip()) for ent in doc.ents
                 if 3 <= len(ent.text.strip()) <= 80
                 and not any(s in ent.text.lower() for s in ["read more", "click here", "from", "this", "it is", "we are"])
                 and ent.label_ not in {"DATE", "TIME", "PERCENT", "MONEY", "QUANTITY"}})

# === Triplet Scoring ===
def score_triplet(subj, pred, obj):
    score = 1.0
    if pred.lower() in {"ist erwähnt in", "kommt aus"}:
        score -= 0.4
    if "[RESOLVE_ME]" in subj or "[RESOLVE_ME]" in obj:
        score -= 0.3
    if subj.istitle():
        score += 0.2
    if obj.istitle():
        score += 0.2
    return max(0.0, min(score, 1.0))

# === Entity Typing ===
def get_entity_type(entity):
    doc = nlp(entity)
    for ent in doc.ents:
        if ent.text.strip().lower() in entity.lower():
            return ent.label_
    return "Unknown"

def classify_entity(entity, spacy_label):
    text = entity.lower()
    if any(kw in text for kw in ["studiengang", "programm", "logistikstudium"]): return "PROGRAM"
    if any(kw in text for kw in ["modul", "bachelorarbeit"]): return "MODULE"
    if any(kw in text for kw in ["thema", "kompetenz", "fach"]): return "TOPIC"
    if any(kw in text for kw in ["labor", "raum"]): return "RESOURCE"
    if any(kw in text for kw in ["fakultät", "hochschule", "universität"]): return "ORG"
    if any(kw in text for kw in ["bayern", "europa", "stadt"]): return "LOC"
    if any(kw in text for kw in ["kontakt", "telefon"]): return "CONTACT"
    if any(kw in text for kw in ["zertifikat", "urkunde"]): return "CERT"
    if any(kw in text for kw in ["student", "dozent", "professor"]): return "PER"
    if spacy_label in {"PER", "ORG", "LOC", "MISC"}:
        return spacy_label
    return "MISC"

# === Triplet Construction ===
def generate_labeled_triplet(subj, pred, obj):
    subj = normalize_entity(subj)
    obj = normalize_entity(obj)
    spacy_subj = get_entity_type(subj)
    spacy_obj = get_entity_type(obj)
    subj_type = classify_entity(subj, spacy_subj)
    obj_type = classify_entity(obj, spacy_obj)
    confidence = score_triplet(subj, pred, obj)
    return {
        "subject": subj,
        "subject_type": subj_type,
        "relation": pred,
        "object": obj,
        "object_type": obj_type,
        "confidence": round(confidence, 2),
        "origin": "llm"
    }

def generate_labeled_triplet_with_metadata(subj, pred, obj, metadata):
    triplet = generate_labeled_triplet(subj, pred, obj)
    triplet["source_metadata"] = {
        "title": metadata.get("title", ""),
        "source": metadata.get("source", ""),
        "type": metadata.get("type", ""),
        "lang": metadata.get("lang", ""),
        "date_updated": metadata.get("date_updated", ""),
        "chunk_id": metadata.get("chunk_id", "")
    }
    return triplet

# === JSON I/O ===
def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

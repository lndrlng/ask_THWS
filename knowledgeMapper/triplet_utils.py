
import json
import os
import re
import spacy
from rapidfuzz import fuzz

nlp = spacy.load("de_core_news_md")
DEBUG = False

# === Unified Entity Normalization + Deduplication ===
entity_cache = {}

def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip() if isinstance(text, str) else ""

def strip_titles(name: str) -> str:
    blacklist = {"prof.", "dr.", "herr", "frau"}
    return " ".join(t for t in name.lower().split() if t not in blacklist).title()

def normalize_entity(entity: str) -> str:
    entity = clean_text(entity)
    entity = re.sub(r"Prof(essor)?(\\.?) Dr(\\.?)?", "", entity, flags=re.IGNORECASE).strip()
    synonyms = {
        "USA": "USA", "U.S.": "USA", "United States": "USA",
        "Student:innen": "Studierende", "Studierenden": "Studierende", "Studenten": "Studierende",
        "Lernende": "Studierende", "COVID-19": "COVID-19-Pandemie", "Corona": "COVID-19-Pandemie",
        "Kliniker*innen": "Kliniker", "Ärzt*innen": "Ärztinnen und Ärzte",
        "Gesundheitsdienstleister*innen": "Gesundheitspersonal", "Autorengruppe": "Forschungsgruppe",
        "Forscher*innengruppe": "Forschungsgruppe"
    }
    entity = synonyms.get(entity, strip_titles(entity))
    for known in entity_cache:
        if fuzz.ratio(entity.lower(), known.lower()) > 90:
            return entity_cache[known]
    entity_cache[entity] = entity
    return entity

# === TRIPLET PROCESSING ===
def is_valid_triplet(line: str) -> bool:
    return re.match(r"^\(.+?,.+?,.+?\)$", line)

def parse_triplets(text: str):
    triplets = []
    matches = re.findall(r"\(([^()]+?,[^()]+?,[^()]+?)\)", text)
    for match in matches:
        try:
            subj, pred, obj = map(str.strip, match.split(",", 2))
            subj = normalize_entity(subj)
            obj = normalize_entity(obj)
            if subj.lower() in {"es", "er", "sie", "dies", "diese", "dieser", "they", "it", "he", "she"}:
                subj = "[RESOLVE_ME]"
            triplets.append((subj, pred, obj))
        except Exception:
            continue
    return triplets

# === NER ENRICHMENT ===
def enrich_with_ner(text: str):
    doc = nlp(text)
    return list({normalize_entity(ent.text.strip()) for ent in doc.ents if 2 <= len(ent.text.strip()) <= 100})

# === SCORING ===
def score_triplet(subj: str, pred: str, obj: str) -> float:
    score = 1.0
    weak_preds = {"ist erwähnt in", "kommt aus"}
    if pred.lower() in weak_preds:
        score -= 0.4
    if "[RESOLVE_ME]" in subj or "[RESOLVE_ME]" in obj:
        score -= 0.3
    if subj.istitle():
        score += 0.2
    if obj.istitle():
        score += 0.2
    return max(0.0, min(score, 1.0))

# === FILE HELPERS ===
def load_json(path: str):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_json(data, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# === ENTITY TYPE DETECTION ===
def get_entity_type(entity: str) -> str:
    doc = nlp(entity)
    for ent in doc.ents:
        if ent.text.strip().lower() in entity.lower():
            return ent.label_
    return "Unknown"

def classify_entity(entity: str, spacy_label: str) -> str:
    text = entity.lower()
    if any(kw in text for kw in ["studiengang", "twin-programm", "logistikstudium"]):
        return "PROGRAM"
    if any(kw in text for kw in ["bachelorarbeit", "praxissemester", "grundstudium", "modul"]):
        return "MODULE"
    if any(kw in text for kw in ["projektarbeit", "lehrinhalt", "thema", "kompetenz", "fach", "wissen"]):
        return "TOPIC"
    if any(kw in text for kw in ["labor", "ressource", "werkstatt", "geräte", "raum"]):
        return "RESOURCE"
    if any(kw in text for kw in ["fakultät", "hochschule", "universität", "schule", "institut"]):
        return "ORG"
    if any(kw in text for kw in ["bayern", "mainfranken", "europa", "stadt", "ort"]):
        return "LOC"
    if any(kw in text for kw in ["kontakt", "telefon", "email"]):
        return "CONTACT"
    if any(kw in text for kw in ["zertifikat", "abschluss", "urkunde"]):
        return "CERT"
    if any(kw in text for kw in ["student", "dozent", "professor", "leiter", "bewerber", "absolvent"]):
        return "PER"
    if spacy_label in {"PER", "ORG", "LOC", "MISC"}:
        return spacy_label
    return "MISC"

def generate_labeled_triplet(subj: str, pred: str, obj: str):
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

# Optional: Label descriptions for documentation or export
LABEL_DESCRIPTIONS = {
    "PROGRAM": "Studiengänge und akademische Programme",
    "MODULE": "Bestandteile von Studienprogrammen wie Module, Praktika oder Abschlussarbeiten",
    "TOPIC": "Fachspezifische Inhalte, Kompetenzen oder Themen",
    "RESOURCE": "Physische oder digitale Ressourcen (z. B. Labore, Räume)",
    "ORG": "Organisationen, Hochschulen, Fakultäten etc.",
    "LOC": "Geografische Orte oder Regionen",
    "CONTACT": "Kontaktinformationen",
    "CERT": "Zertifikate, Abschlüsse oder Urkunden",
    "PER": "Individuen wie Studenten, Professoren oder Bewerber",
    "MISC": "Sonstige nicht klassifizierte Begriffe"
}


def generate_labeled_triplet_with_metadata(subj: str, pred: str, obj: str, metadata: dict):
    triplet = generate_labeled_triplet(subj, pred, obj)
    triplet["source_metadata"] = {
        "title": metadata.get("title", ""),
        "source": metadata.get("source", ""),
        "type": metadata.get("type", ""),
        "lang": metadata.get("lang", ""),
        "date_updated": metadata.get("date_updated", "")
    }
    return triplet

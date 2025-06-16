# File: knowledgeMapper/retrieval.py
# Description: v5.1 - Corrected version. Reverted to robust prompt and hybrid mode to ensure compatibility.

import re
from datetime import datetime
from typing import List, Dict
from lightrag import LightRAG
from lightrag.base import QueryParam
from knowledgeMapper.local_models import OllamaLLM

PROTECTED_KEYWORDS = [
    "Mensa", "SPO", "HiWi", "THWS", "Würzburg", "Schweinfurt",
    "BIN", "BEC", "BWI", "E-Commerce", "Cybersecurity"
]

#Specifies the retrieval mode:
#- "local": Focuses on context-dependent information.
#- "global": Utilizes global knowledge.
#- "hybrid": Combines local and global retrieval methods.
#- "naive": Performs a basic search without advanced techniques.
#- "mix": Integrates knowledge graph and vector retrieval.

MODE = "hybrid"
# ==============================================================================
# FINAL ROBUST SYSTEM PROMPT v5
# This version uses direct, command-like instructions.
# ==============================================================================
FINAL_SYSTEM_PROMPT_TEMPLATE = """
**SYSTEMBEFEHL:**
1.  **ANTWORTE NUR AUF DEUTSCH.** Dies ist die wichtigste Regel. Deine Ausgabe an den Nutzer muss immer Deutsch sein.
2.  **NUTZE AUSSCHLIESSLICH DEN KONTEXT.** Deine Antwort darf nur Informationen aus dem `KONTEXT` enthalten. Eigenes Wissen ist verboten.
3.  **WENN DIE ANTWORT NICHT IM KONTEXT STEHT:** Antworte NUR mit dem Satz: "Ich konnte keine passenden Informationen zu Ihrer Anfrage in meiner Wissensdatenbank finden." Erfinde nichts.
4.  **QUELLENANGABE:** Am Ende deiner Antwort, füge eine `🔗 Quellen:` Sektion hinzu. Liste dort die `file_path` oder `source_id` der genutzten Kontexte auf.

---
**ZUSATZDATEN:**
- Heutiges Datum: {current_date}
- Standort: {location}
---
**NUTZERFRAGE:**
{user_query}
---
**KONTEXT:**
{{context_data}}
"""


def _hybrid_translate(text: str, keywords: List[str]) -> (str, Dict[str, str]):
    """Replaces keywords with placeholders for safe translation."""
    placeholders = {}
    for i, keyword in enumerate(keywords):
        if re.search(r'\b' + re.escape(keyword) + r'\b', text, re.IGNORECASE):
            placeholder = f"__KEYWORD_{i}__"
            text = re.sub(r'\b' + re.escape(keyword) + r'\b', placeholder, text, flags=re.IGNORECASE)
            placeholders[placeholder] = keyword
    return text, placeholders


def _restore_keywords(text: str, placeholders: Dict[str, str]) -> str:
    """Restores original keywords from placeholders."""
    for placeholder, keyword in placeholders.items():
        text = text.replace(placeholder, keyword)
    return text


def _post_process_answer(text: str) -> str:
    """Cleans up common LLM formatting errors."""
    # Removes the weirdly formatted "Sources are now included..." string
    # Fixes concatenated words like "WortWort" -> "Wort Wort"
    text = re.sub(r'([a-zäöüß])([A-ZÄÖÜ])', r'\1 \2', text)
    # Removes any remaining weirdly spaced out words like "L - M ."
    text = re.sub(r'\b(\w)\s*-\s*(?=\w\b)', r'\1', text)
    return text.strip()


async def prepare_and_execute_retrieval(
        user_query: str,
        rag_instance: LightRAG,
        llm_instance: OllamaLLM
) -> str:
    """
    Orchestrates the retrieval process with keyword protection, robust prompting, and post-processing.
    Optionally skips English translation for retrieval if direct German retrieval is desired.
    """
    print("1. Preparing query (keywords will be restored if needed)...")
    # Keywords werden immer noch geschützt, falls sie im generierten Prompt oder der Antwort erscheinen.
    query_with_placeholders, placeholders = _hybrid_translate(user_query, PROTECTED_KEYWORDS)

    # --- START HIER DIE ÄNDERUNG ---
    # Option 1: Beibehaltung der englischen Übersetzung für Retrieval (aktueller Ansatz)
    # print("2. Translating query to English for retrieval...")
    # translation_prompt = f"Translate the following German text to English. Respond with ONLY the translated text, without any explanation or introductory phrases. German text: \"{query_with_placeholders}\""
    # english_query_placeholders = await llm_instance(prompt=translation_prompt)
    # query_for_retrieval = _restore_keywords(english_query_placeholders.strip(), placeholders)
    # print(f"   - Final English query for retrieval: '{query_for_retrieval}'")

    # Option 2: Direkte Verwendung der deutschen Query für Retrieval (empfohlen zum Testen)
    print("2. Using original German query for retrieval (skipping English translation)..")
    query_for_retrieval = _restore_keywords(query_with_placeholders, placeholders)
    print(f"   - Final German query for retrieval: '{query_for_retrieval}'")
    # --- ENDE DER ÄNDERUNG ---

    print("3. Injecting dynamic context and crafting final prompt...")
    current_date = datetime.now().strftime("%d. %B %Y")
    final_system_prompt = FINAL_SYSTEM_PROMPT_TEMPLATE.format(
        current_date=current_date,
        location="Würzburg/Schweinfurt",
        user_query=user_query  # Hier wird die originale deutsche Nutzerfrage verwendet
    )

    print(f"4. Executing controlled query with LightRAG using '{MODE}' mode...")
    params = QueryParam(
        mode=MODE,  # vector + BM25 + KG
        user_prompt=final_system_prompt,
        top_k=20
    )
    # Die Query an LightRAG ist jetzt die deutsche Query
    final_answer = await rag_instance.aquery(query_for_retrieval, param=params)  #
    print("   - Raw answer generated.")

    print("5. Post-processing the final answer...")
    cleaned_answer = _post_process_answer(final_answer)  #
    print("   - Final answer cleaned and finalized.")

    return cleaned_answer

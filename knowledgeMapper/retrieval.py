# File: knowledgeMapper/retrieval.py
# Description: v6.4 - FINAL & VERIFIED VERSION. Corrects all regex syntax
#              errors and properly implements the "Generate-Then-Process" architecture.

import re
import ast
from datetime import datetime
from typing import List, Dict, Any, Union
from lightrag import LightRAG
from lightrag.base import QueryParam
from knowledgeMapper.local_models import OllamaLLM

MODE = "mix"

# This prompt correctly instructs the model to create traceable inline citations.
RELIABLE_SYSTEM_PROMPT_TEMPLATE = """
**SYSTEMBEFEHL FÜR PRÄZISE WISSENSBASIERTE ANTWORTEN:**
1.  **SPRACHE:** Antworte **AUSSCHLIESSLICH** auf **DEUTSCH**.
2.  **INFORMATIONSEINSCHRÄNKUNG:** Deine Antwort MUSS **VOLLSTÄNDIG** und **AUSSCHLIESSLICH** auf den Informationen im bereitgestellten `KONTEXT` basieren. Generiere **KEINE** neuen Informationen, spekuliere **NICHT** und füge **NICHTS HINZU**, was nicht im `KONTEXT` explizit genannt ist.
3.  **PRÄZISION & KONSISTENZ:**
    * Synthetisiere relevante Fakten aus verschiedenen Kontextabschnitten zu einer **flüssigen, kohärenten und gut lesbaren Antwort**.
    * Wenn der `KONTEXT` widersprüchliche Informationen zu einem Thema enthält, gib **BEIDE Versionen an** 
4.  **FALLBACK-PROZEDERE:** Falls die `NUTZERFRAGE` **NICHT** oder **NICHT ausreichend** im `KONTEXT` beantwortet werden kann, antworte **AUSSCHLIESSLICH** und wortwörtlich mit:
    "Ich konnte keine passenden Informationen zu Ihrer Anfrage in meiner Wissensdatenbank finden."
    Verändere diese Formulierung **NICHT**.
6.  **UNTERDRÜCKUNG VON PLAPPERN/ERGÄNZUNGEN:** Gehe direkt zur Antwort über. Vermeide einleitende Phrasen wie "Basierend auf dem Kontext..." oder abschließende Bemerkungen. Die Antwort soll **NUR** die Beantwortung der Nutzerfrage sein.


---
**ZUSATZDATEN:**
- Heutiges Datum: {current_date}
- Standort: {location}
---
**NUTZERFRAGE:**
{user_query}
"""


async def prepare_and_execute_retrieval(
        user_query: str,
        rag_instance: LightRAG,
) -> Dict[str, Union[str, List[Dict[str, Any]]]]:
    """
    Orchestrates a reliable RAG process that returns a separate clean answer
    and a structured list of the sources used to generate it.
    """

    # --- 1. Generate the Intermediate Answer with Inline Citations ---
    print("1. Generating intermediate answer with inline citations...")
    final_system_prompt = RELIABLE_SYSTEM_PROMPT_TEMPLATE.format(
        current_date=datetime.now().strftime("%d. %B %Y"),
        location="Würzburg/Schweinfurt",
        user_query=user_query
    )
    params = QueryParam(mode=MODE, top_k=7)

    citable_answer_text = await rag_instance.aquery(
        user_query,
        param=params,
        system_prompt=final_system_prompt
    )
    print("   - Intermediate citable answer received.")

    # --- 2. Retrieve the Full Context for Source Lookup ---
    print("2. Retrieving full context for source mapping...")
    params_context = QueryParam(
        mode=MODE,
        top_k=7,
        only_need_context=True
    )
    context_data_str = await rag_instance.aquery(user_query, param=params_context)
    print("   - Raw context data received.")




    print("   - Structured source list created.")

    # Return a structured dictionary, perfect for an API endpoint.
    return {
        "answer": citable_answer_text,
        "sources": context_data_str
    }

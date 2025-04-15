import spacy
import coreferee

def load_coref_model():
    print("🧠 Loading spaCy with coreferee (German)...")
    nlp = spacy.load("de_core_news_md")

    try:
        nlp.add_pipe("coreferee")
        print("✅ Coreference model loaded.")
    except Exception as e:
        print(f"❌ Failed to add coreferee: {e}")
        raise e

    return nlp

nlp = load_coref_model()

def resolve_coreferences(text: str) -> str:
    try:
        doc = nlp(text)
        if not hasattr(doc._, "has_coref") or not doc._.has_coref:
            return text

        replacements = {}
        for chain in doc._.coref_chains:
            main = chain.main.text
            for mention in chain:
                if mention != chain.main:
                    replacements[mention.start] = main

        resolved_tokens = []
        for i, token in enumerate(doc):
            resolved_tokens.append(replacements.get(i, token.text))

        return " ".join(resolved_tokens)

    except Exception as e:
        print(f"⚠️ Coreference resolution error: {e}")
        return text

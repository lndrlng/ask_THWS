from urllib.parse import parse_qs, urlparse

from langdetect import DetectorFactory
from langdetect import detect as langdetect_detect

DetectorFactory.seed = 42


def extract_lang_from_url(url: str) -> str:
    """
    Detect language from:
    - ?lang=de (query string)
    - /en/, /de/, /us/ (first path segment)
    Normalizes known aliases (e.g. 'us' → 'en').
    Falls back to 'unknown'.
    """
    parsed = urlparse(url)

    # Aliases map
    lang_aliases = {
        "us": "en",
    }

    # Check query string: ?lang=de
    qs_lang = parse_qs(parsed.query).get("lang", [None])[0]
    if qs_lang:
        return lang_aliases.get(qs_lang.lower(), qs_lang.lower())

    # Check first path segment
    segments = parsed.path.strip("/").split("/")
    if segments:
        segment = segments[0].lower()
        if segment in {"en", "de", "us"}:
            return lang_aliases.get(segment, segment)

    return "unknown"


def detect_lang_from_content(text_content: str, min_length: int = 50) -> str:
    """
    Detects language from the given text content using langdetect.
    Returns the language code (e.g., 'en', 'de') or 'unknown'.
    Assumes text_content is already plain text.
    """
    if not text_content or not isinstance(text_content, str):
        return "unknown"

    plain_text = text_content.strip()

    if len(plain_text) < min_length:
        return "unknown"

    try:
        lang = langdetect_detect(plain_text)
        return lang
    except Exception:
        return "unknown"

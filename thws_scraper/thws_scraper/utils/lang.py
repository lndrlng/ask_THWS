from urllib.parse import parse_qs, urlparse


def extract_lang_from_url(url: str) -> str:
    """
    Detect language from:
    - ?lang=de (query string)
    - /en/, /de/ (first path segment)
    Falls back to 'unknown'.
    """
    parsed = urlparse(url)

    # Check query string: ?lang=de
    qs_lang = parse_qs(parsed.query).get("lang", [None])[0]
    if qs_lang:
        return qs_lang

    # Check first path segment: /en/ or /de/
    segments = parsed.path.strip("/").split("/")
    if segments and segments[0] in {"en", "de"}:
        return segments[0]

    return "unknown"

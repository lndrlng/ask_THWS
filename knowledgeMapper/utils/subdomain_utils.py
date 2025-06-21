import re
from urllib.parse import urlparse


def get_sanitized_subdomain(url: str | None) -> str | None:
    """
    Parses a URL to extract the netloc (e.g., 'sub.example.com')
    and sanitizes it for use as a directory name.

    Returns 'default' if the URL is invalid or missing.
    """
    if not url:
        return "default"
    try:
        netloc = urlparse(url).netloc
        if not netloc:
            return "default"
        # Sanitize for filesystem: replace dots and invalid chars with underscores
        return re.sub(r"[^a-zA-Z0-9_-]", "_", netloc)
    except Exception:
        return "default"

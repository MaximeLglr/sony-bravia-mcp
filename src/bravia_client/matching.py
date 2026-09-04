from __future__ import annotations

import html


def clean_title(raw: str) -> str:
    """Decode HTML entities and collapse whitespace in a TV-provided label."""
    return " ".join(html.unescape(raw).replace("\u00a0", " ").split())

from __future__ import annotations

import re

from fastapi import HTTPException

_MAX_QUERY_LEN = 2000
_MIN_QUERY_LEN = 5

_INJECTION_PATTERNS = re.compile(
    r"(--|;|\bDROP\b|\bSELECT\b|\bINSERT\b|\bDELETE\b|\bUPDATE\b"
    r"|\bEXEC\b|\bUNION\b|<script|javascript:|onerror=)",
    re.IGNORECASE,
)


def validate_query(query: str) -> str:
    """Sanitize and validate a user query string. Raises HTTPException on violation."""
    query = query.strip()

    if len(query) < _MIN_QUERY_LEN:
        raise HTTPException(status_code=400, detail=f"Query too short (minimum {_MIN_QUERY_LEN} chars).")

    if len(query) > _MAX_QUERY_LEN:
        raise HTTPException(status_code=400, detail=f"Query too long (maximum {_MAX_QUERY_LEN} chars).")

    if _INJECTION_PATTERNS.search(query):
        raise HTTPException(status_code=400, detail="Query contains disallowed patterns.")

    # Collapse excessive whitespace
    query = re.sub(r"\s{3,}", "  ", query)

    return query

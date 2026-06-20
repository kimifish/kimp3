#  -*- coding: utf-8 -*-
# pyright: basic
# pyright: reportAttributeAccessIssue=false

import logging
import re
from difflib import SequenceMatcher

from kimp3.config import cfg, APP_NAME

log = logging.getLogger(f"{APP_NAME}.{__name__}")

ALBUM_TITLE_MATCH_THRESHOLD = 0.78
ALBUM_TITLE_BASE_WEIGHT = 0.85
_TRAILING_PARENS_RE = re.compile(r"\s*\(([^()]*)\)\s*$")


def sanitize_path_component(value: str) -> str:
    """Sanitizes string by removing characters invalid in file paths.
    
    Args:
        value: Input string
        
    Returns:
        Sanitized string safe for use in file paths
    """
    # Заменяем слеши на дефисы
    value = value.replace('/', '-').replace('\\', '-')
    
    # Заменяем другие недопустимые символы
    invalid_chars = '<>:"|?*'
    for char in invalid_chars:
        value = value.replace(char, '')
        
    # Убираем точки в конце строки (проблема в Windows)
    value = value.rstrip('.')
    
    # Убираем пробелы в начале и конце
    value = value.strip()
    
    return value if value else 'Unknown'


def normalize_string(s: str) -> str:
    """Convert string to normalized form for comparison.
    
    Args:
        s: Input string
        
    Returns:
        Normalized string containing only lowercase alphanumeric characters
    """
    return ''.join(c.lower() for c in s if c.isalnum())


def string_similarity(str1: str, str2: str, min_ratio: float = 0.5) -> float:
    """Compare strings using SequenceMatcher.
    
    Args:
        str1: First string to compare
        str2: Second string to compare
        min_ratio: Minimum similarity ratio (0.0 to 1.0)
        
    Returns:
        Similarity ratio
    """
    result = SequenceMatcher(None, str1.lower(), str2.lower()).ratio()
    return result if result > min_ratio else 0


def split_album_title(title: str) -> tuple[str, str]:
    """Split an album title into primary title and trailing parenthetical qualifier."""
    base = title.strip()
    qualifiers: list[str] = []

    while True:
        match = _TRAILING_PARENS_RE.search(base)
        if not match:
            break
        qualifiers.insert(0, match.group(1).strip())
        base = base[: match.start()].strip()

    return base or title.strip(), " ".join(item for item in qualifiers if item)


def _casefolded_ratio(str1: str, str2: str) -> float:
    if not str1 and not str2:
        return 1.0
    if not str1 or not str2:
        return 0.0
    return SequenceMatcher(None, str1.casefold(), str2.casefold()).ratio()


def album_title_similarity(
    candidate: str,
    query: str,
    min_ratio: float = ALBUM_TITLE_MATCH_THRESHOLD,
) -> float:
    """Compare album titles while treating parenthetical qualifiers as weak evidence."""
    candidate_base, candidate_qualifier = split_album_title(candidate)
    query_base, query_qualifier = split_album_title(query)

    base_ratio = _casefolded_ratio(candidate_base, query_base)
    if candidate_qualifier and query_qualifier:
        qualifier_ratio = _casefolded_ratio(candidate_qualifier, query_qualifier)
    elif candidate_qualifier == query_qualifier:
        qualifier_ratio = 1.0
    else:
        qualifier_ratio = 0.0

    score = base_ratio * ALBUM_TITLE_BASE_WEIGHT + qualifier_ratio * (
        1.0 - ALBUM_TITLE_BASE_WEIGHT
    )
    return score if score >= min_ratio else 0.0

#  -*- coding: utf-8 -*-
# pyright: basic
# pyright: reportAttributeAccessIssue=false

import logging
from difflib import SequenceMatcher
from kimp3.config import cfg, APP_NAME

log = logging.getLogger(f"{APP_NAME}.{__name__}")


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


def string_similarity(str1: str, str2: str, min_ratio: float = 0.8) -> bool:
    """Compare strings using SequenceMatcher.
    
    Args:
        str1: First string to compare
        str2: Second string to compare
        min_ratio: Minimum similarity ratio (0.0 to 1.0)
        
    Returns:
        True if similarity ratio >= min_ratio
    """
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio() >= min_ratio

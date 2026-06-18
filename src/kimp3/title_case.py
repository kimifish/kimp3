from __future__ import annotations

import re
from typing import Iterable, Literal

from kimp3.models import AudioTags


TitleNormalization = Literal["preserve", "title_case_safe", "aggressive_normalize"]

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_RE = re.compile(r"[A-Za-z]")
SPACE_RE = re.compile(r"\s+")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’]*(?:[./-][A-Za-z][A-Za-z'’]*)*\.?")
EXCEPTION_BOUNDARY = r"A-Za-zА-Яа-яЁё0-9"

SMALL_WORDS = {
    "a",
    "an",
    "the",
    "and",
    "but",
    "or",
    "nor",
    "for",
    "so",
    "yet",
    "as",
    "at",
    "by",
    "from",
    "in",
    "into",
    "of",
    "on",
    "onto",
    "to",
    "with",
    "without",
    "over",
    "under",
    "through",
    "between",
    "among",
}


def _collapse_spaces(value: str) -> str:
    return SPACE_RE.sub(" ", value.strip())


def _contains_cyrillic(value: str) -> bool:
    return bool(CYRILLIC_RE.search(value))


def _contains_latin(value: str) -> bool:
    return bool(LATIN_RE.search(value))


def _exception_map(exceptions: Iterable[str]) -> dict[str, str]:
    return {item.casefold(): item for item in exceptions if item.strip()}


def _protect_exceptions(
    value: str, exceptions: Iterable[str], *, phrase_only: bool = False
) -> tuple[str, dict[str, str]]:
    protected = value
    replacements: dict[str, str] = {}
    protected_exceptions = sorted(
        {
            item
            for item in exceptions
            if item.strip() and (not phrase_only or " " in item.strip())
        },
        key=len,
        reverse=True,
    )
    for index, exception in enumerate(protected_exceptions):
        placeholder = f"\x00§{index}§\x00"
        pattern = re.compile(
            rf"(?<![{EXCEPTION_BOUNDARY}]){re.escape(exception)}(?![{EXCEPTION_BOUNDARY}])",
            re.IGNORECASE,
        )
        protected = pattern.sub(placeholder, protected)
        replacements[placeholder] = exception
    return protected, replacements


def _restore_exceptions(value: str, replacements: dict[str, str]) -> str:
    restored = value
    for placeholder, exception in replacements.items():
        restored = restored.replace(placeholder, exception)
    return restored


def _starts_with_placeholder(value: str, replacements: dict[str, str]) -> bool:
    stripped = value.lstrip(" \t\n\r'\"([{«")
    return any(stripped.startswith(placeholder) for placeholder in replacements)


def _apply_exceptions_only(value: str, exceptions: Iterable[str]) -> str:
    result = value
    for exception in sorted({item for item in exceptions if item.strip()}, key=len, reverse=True):
        pattern = re.compile(
            rf"(?<![{EXCEPTION_BOUNDARY}]){re.escape(exception)}(?![{EXCEPTION_BOUNDARY}])",
            re.IGNORECASE,
        )
        result = pattern.sub(exception, result)
    return result


def _is_stylized_token(token: str) -> bool:
    if any(char.isdigit() for char in token):
        return True
    if any(char in token for char in (".", "/")):
        return True
    if token.startswith("!"):
        return True
    letters = [char for char in token if char.isalpha()]
    if not letters:
        return True
    return any(char.islower() for char in letters) and any(
        char.isupper() for char in letters[1:]
    )


def _capitalize_word(word: str) -> str:
    for index, char in enumerate(word):
        if char.isalpha():
            return f"{word[:index]}{char.upper()}{word[index + 1:].lower()}"
    return word


def _normalize_word(
    word: str,
    *,
    is_first: bool,
    is_last: bool,
    exceptions: dict[str, str],
    preserve_stylized: bool,
) -> str:
    exception = exceptions.get(word.casefold())
    if exception is not None:
        return exception
    if preserve_stylized and _is_stylized_token(word):
        return word
    if not is_first and not is_last and word.casefold() in SMALL_WORDS:
        return word.lower()
    return _capitalize_word(word)


def _normalize_hyphenated_word(
    word: str,
    *,
    is_first: bool,
    is_last: bool,
    exceptions: dict[str, str],
    preserve_stylized: bool,
) -> str:
    exception = exceptions.get(word.casefold())
    if exception is not None:
        return exception
    if preserve_stylized and _is_stylized_token(word):
        return word

    parts = word.split("-")
    if len(parts) == 1:
        return _normalize_word(
            word,
            is_first=is_first,
            is_last=is_last,
            exceptions=exceptions,
            preserve_stylized=preserve_stylized,
        )

    normalized = []
    for index, part in enumerate(parts):
        normalized.append(
            _normalize_word(
                part,
                is_first=is_first and index == 0,
                is_last=is_last and index == len(parts) - 1,
                exceptions=exceptions,
                preserve_stylized=preserve_stylized,
            )
        )
    return "-".join(normalized)


def title_case_safe(value: str, exceptions: Iterable[str] = ()) -> str:
    """Return moderate English Title Case."""
    text = _collapse_spaces(value)
    if not text:
        return text

    exceptions_map = _exception_map(exceptions)
    phrase_exception = exceptions_map.get(text.casefold())
    if phrase_exception is not None:
        return phrase_exception
    text, protected_exceptions = _protect_exceptions(text, exceptions, phrase_only=True)

    matches = list(WORD_RE.finditer(text))
    if not matches:
        return _restore_exceptions(text, protected_exceptions)

    result = []
    position = 0
    for index, match in enumerate(matches):
        result.append(text[position : match.start()])
        result.append(
            _normalize_hyphenated_word(
                match.group(0),
                is_first=index == 0,
                is_last=index == len(matches) - 1,
                exceptions=exceptions_map,
                preserve_stylized=True,
            )
        )
        position = match.end()
    result.append(text[position:])
    return _restore_exceptions("".join(result), protected_exceptions)


def sentence_case_safe(value: str, exceptions: Iterable[str] = ()) -> str:
    """Return Russian-style sentence case while preserving configured names."""
    text = _collapse_spaces(value)
    if not text:
        return text

    exceptions_map = _exception_map(exceptions)
    phrase_exception = exceptions_map.get(text.casefold())
    if phrase_exception is not None:
        return phrase_exception

    text, protected_exceptions = _protect_exceptions(text, exceptions)
    text = _apply_exceptions_only(text.lower(), exceptions)
    if not _starts_with_placeholder(text, protected_exceptions):
        for index, char in enumerate(text):
            if char.isalpha():
                text = f"{text[:index]}{char.upper()}{text[index + 1:]}"
                break
    return _restore_exceptions(text, protected_exceptions)


def normalize_title(value: str, mode: TitleNormalization, exceptions: Iterable[str]) -> str:
    text = _collapse_spaces(value)
    if mode == "preserve":
        return text
    has_cyrillic = _contains_cyrillic(text)
    has_latin = _contains_latin(text)
    if has_cyrillic and has_latin:
        return _apply_exceptions_only(text, exceptions)
    if has_cyrillic:
        return sentence_case_safe(text, exceptions)
    if mode == "aggressive_normalize":
        return title_case_safe(text, exceptions)
    return title_case_safe(text, exceptions)


def normalize_audio_tag_titles(tags: AudioTags, tags_config: object) -> AudioTags:
    """Return a copy with normalized human-readable title fields only."""
    mode = getattr(tags_config, "title_normalization", "title_case_safe")
    exceptions = getattr(tags_config, "title_case_exceptions", [])
    normalized = tags.model_copy(deep=True)
    for field in ("title", "artist", "album", "album_artist"):
        setattr(normalized, field, normalize_title(getattr(normalized, field), mode, exceptions))
    return normalized

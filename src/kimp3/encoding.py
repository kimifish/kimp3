from __future__ import annotations

from kimp3.models import AudioTags, Lyrics


CYRILLIC_RANGES = (("а", "я"), ("А", "Я"), ("ё", "ё"), ("Ё", "Ё"))
MOJIBAKE_MARKERS = set("ÃÂÐÑÏðèòàåîíñëêóçäìáќєўї")


def _count_cyrillic(value: str) -> int:
    return sum(any(start <= char <= end for start, end in CYRILLIC_RANGES) for char in value)


def _text_score(value: str) -> int:
    cyrillic = _count_cyrillic(value)
    markers = sum(char in MOJIBAKE_MARKERS for char in value)
    utf8_cp1251_markers = sum(value.count(marker) for marker in ("Рџ", "Рђ", "Рё", "Рµ", "С‚", "СЂ", "СЃ", "СЊ", "СЋ", "СЏ"))
    controls = sum(ord(char) < 32 and char not in "\t\n\r" for char in value)
    replacements = value.count("�")
    return cyrillic * 4 - markers * 2 - utf8_cp1251_markers * 8 - controls * 5 - replacements * 10


def _decode_latin1_as_cp1251(value: str) -> str | None:
    try:
        return value.encode("latin1").decode("cp1251")
    except UnicodeError:
        return None


def _decode_cp1251_as_utf8(value: str) -> str | None:
    try:
        return value.encode("cp1251").decode("utf-8")
    except UnicodeError:
        return None


def repair_cp1251_mojibake(value: str) -> str:
    """Repair common Cyrillic mojibake when the result is clearly better."""
    if not value:
        return value
    candidates = [candidate for candidate in (_decode_latin1_as_cp1251(value), _decode_cp1251_as_utf8(value)) if candidate]
    best = max(candidates, key=_text_score, default=value)
    if best == value:
        return value
    if _count_cyrillic(best) < 2:
        return value
    if _text_score(best) <= _text_score(value) + 2:
        return value
    return best


def repair_audio_tags_text_encoding(tags: AudioTags) -> AudioTags:
    """Return a copy of tags with repaired Cyrillic mojibake in text fields."""
    repaired = tags.model_copy(deep=True)
    for field in ("title", "artist", "album", "album_artist", "comment"):
        setattr(repaired, field, repair_cp1251_mojibake(getattr(repaired, field)))
    repaired.genres = [repair_cp1251_mojibake(value) for value in repaired.genres]
    repaired.lastfm_tags = [repair_cp1251_mojibake(value) for value in repaired.lastfm_tags]
    if repaired.lyrics:
        repaired.lyrics = Lyrics(
            text=repair_cp1251_mojibake(repaired.lyrics.text),
            language=repaired.lyrics.language,
            description=repair_cp1251_mojibake(repaired.lyrics.description),
        )
    return repaired

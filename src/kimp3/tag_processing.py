from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import List, Literal
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import pylast
import requests

from kimp3.config import APP_NAME, cfg

NUMBER_OF_TAGS = 15
TAG_MIN_WEIGHT = 10

log = logging.getLogger(f"{APP_NAME}.{__name__}")

TagSource = Literal[
    "lastfm_track",
    "lastfm_album",
    "lastfm_artist",
    "llm_genre",
    "llm_tag",
    "existing_genre",
    "existing_tag",
]

LASTFM_SOURCES = {"lastfm_track", "lastfm_album", "lastfm_artist"}


@dataclass(frozen=True)
class TagCandidate:
    name: str
    source: TagSource
    weight: int | None = None


@dataclass(frozen=True)
class LlmTagSuggestions:
    genres: list[str]
    tags: list[str]


@dataclass
class AggregatedTag:
    name: str
    sources: set[TagSource]
    score: float
    first_index: int


def _split_existing(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return [item.strip().lower() for item in value if item.strip()]
    return [item.strip().lower() for item in re.split("[,/]", value) if item.strip()]


def _lastfm_candidates(
    tags: List[pylast.TopItem], source: TagSource, num: int
) -> list[TagCandidate]:
    candidates = []
    for tag_obj in tags[:num]:
        try:
            weight = int(tag_obj.weight)
        except (TypeError, ValueError):
            weight = None
        candidates.append(
            TagCandidate(
                name=tag_obj.item.get_name().lower(),
                source=source,
                weight=weight,
            )
        )
    return candidates


def _format_lastfm_tags_for_log(tags: List[pylast.TopItem]) -> list[str]:
    result = []
    for tag_obj in tags:
        try:
            result.append(f"{tag_obj.item.get_name()}:{tag_obj.weight}")
        except AttributeError:
            result.append(str(tag_obj))
    return result


def _normalize_tag(tag: str) -> str:
    for similar_tags in cfg.tags.similar_tags:
        if tag in similar_tags:
            return similar_tags[0]

    for pattern_list in cfg.tags.similar_tags_patterns:
        if any(re.match(pattern, tag) for pattern in pattern_list[1:]):
            return pattern_list[0]

    return tag


def _is_banned_tag(tag: str, artist_name: str) -> bool:
    tag_key = tag.casefold()
    artist_key = artist_name.casefold()
    if tag_key in {item.casefold() for item in cfg.tags.banned_tags}:
        return True
    if any(re.match(pattern, tag) for pattern in cfg.tags.banned_tags_patterns):
        return True
    banned_artists = {
        key.casefold(): [artist.casefold() for artist in artists]
        for key, artists in cfg.tags.banned_artists_from_tags.items()
    }
    if tag_key in banned_artists:
        return artist_key in banned_artists[tag_key]
    return False


def _source_score(candidate: TagCandidate) -> float:
    weight = (candidate.weight or 0) / 100
    if candidate.source == "lastfm_track":
        return weight
    if candidate.source == "lastfm_album":
        return weight * 0.75
    if candidate.source == "lastfm_artist":
        return weight * 0.55
    if candidate.source == "llm_genre":
        return 0.65
    if candidate.source == "llm_tag":
        return 0.45
    if candidate.source == "existing_genre":
        return 0.8
    if candidate.source == "existing_tag":
        return 0.5
    return 0.0


def _aggregate_candidates(
    candidates: list[TagCandidate], artist_name: str, track_title: str
) -> dict[str, AggregatedTag]:
    aggregated: dict[str, AggregatedTag] = {}
    ignored_names = {artist_name.lower(), track_title.lower()}
    for index, candidate in enumerate(candidates):
        tag = candidate.name.strip().lower()
        if tag in ignored_names:
            continue
        if not tag or len(tag) > cfg.tags.max_length:
            continue

        tag = _normalize_tag(tag)
        if _is_banned_tag(tag, artist_name):
            continue

        score = _source_score(candidate)
        if tag not in aggregated:
            aggregated[tag] = AggregatedTag(tag, {candidate.source}, score, index)
            continue

        item = aggregated[tag]
        item.sources.add(candidate.source)
        item.score = min(1.0, max(item.score, score) + 0.15)

    return aggregated


def _public_genres() -> set[str]:
    return (
        set(cfg.tags.genres)
        | set(cfg.tags.extended_genres)
        | set(cfg.tags.genre_parents)
    )


def _genre_parent(tag: str) -> str | None:
    parent = cfg.tags.genre_parents.get(tag)
    if parent in cfg.tags.genres:
        return parent
    return None


def _is_lastfm_confirmed(item: AggregatedTag) -> bool:
    return bool(item.sources & LASTFM_SOURCES)


def _is_llm_confirmed_genre(item: AggregatedTag) -> bool:
    return "llm_genre" in item.sources and item.name in _public_genres()


def _can_promote_parent(item: AggregatedTag) -> bool:
    return bool(
        item.sources
        & (LASTFM_SOURCES | {"llm_genre", "existing_genre", "existing_tag"})
    )


def _select_genres(aggregated: dict[str, AggregatedTag]) -> list[str]:
    candidates: dict[str, AggregatedTag] = {}
    for item in aggregated.values():
        if item.name in cfg.tags.genres:
            if (
                _is_lastfm_confirmed(item)
                or "existing_genre" in item.sources
                or _is_llm_confirmed_genre(item)
            ):
                candidates[item.name] = item
            continue

        parent = _genre_parent(item.name)
        if parent and _can_promote_parent(item):
            candidates.setdefault(
                parent,
                AggregatedTag(
                    parent, set(item.sources), item.score * 0.9, item.first_index
                ),
            )

    ranked = sorted(
        candidates.values(), key=lambda item: (-item.score, item.first_index)
    )
    return [item.name for item in ranked[: cfg.tags.max_genres]]


def _select_tags(aggregated: dict[str, AggregatedTag], genres: list[str]) -> list[str]:
    genre_set = set(genres)
    ranked = sorted(
        aggregated.values(), key=lambda item: (-item.score, item.first_index)
    )
    tags = [item.name for item in ranked if item.name not in genre_set]
    return tags[: cfg.tags.max_tags]


def process_lastfm_tags(
    artist_tags: List[pylast.TopItem],
    album_tags: List[pylast.TopItem],
    track_tags: List[pylast.TopItem],
    existing_genre: str | list[str] = "",
    existing_tags: str | list[str] = "",
    artist_name: str = "",
    track_title: str = "",
    num: int = NUMBER_OF_TAGS,
) -> tuple[list[str], list[str]]:
    """Process Last.FM tags into ordered genre and auxiliary tag lists."""
    candidates: list[TagCandidate] = []

    if cfg.tags.use_llm:
        llm_tags = get_llm_tag_suggestions(artist_name, track_title)
        candidates.extend(TagCandidate(tag, "llm_genre") for tag in llm_tags.genres)
        candidates.extend(TagCandidate(tag, "llm_tag") for tag in llm_tags.tags)

    log.debug(
        "Last.fm tags received for %s - %s: track=%s album=%s artist=%s",
        artist_name,
        track_title,
        _format_lastfm_tags_for_log(track_tags),
        _format_lastfm_tags_for_log(album_tags),
        _format_lastfm_tags_for_log(artist_tags),
    )

    candidates.extend(_lastfm_candidates(track_tags, "lastfm_track", num))
    candidates.extend(_lastfm_candidates(album_tags, "lastfm_album", num))
    candidates.extend(_lastfm_candidates(artist_tags, "lastfm_artist", num))

    if existing_tags:
        candidates.extend(
            TagCandidate(tag, "existing_tag") for tag in _split_existing(existing_tags)
        )
    if existing_genre:
        candidates.extend(
            TagCandidate(tag, "existing_genre")
            for tag in _split_existing(existing_genre)
        )

    aggregated = _aggregate_candidates(candidates, artist_name, track_title)
    result_genre = _select_genres(aggregated)
    result_tags = _select_tags(aggregated, result_genre)

    return result_genre, result_tags


def tags_list_to_str_list(tags: List[pylast.TopItem]) -> List[str]:
    return [tag.item.get_name() for tag in tags]


def _llm_chat_url(llm_url: str) -> str:
    """Return the ai_server v1 chat endpoint for a configured base or legacy URL."""
    parts = urlsplit(llm_url.rstrip("/"))
    if parts.path.rstrip("/") == "/v1/chat":
        return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))
    return urlunsplit((parts.scheme, parts.netloc, "/v1/chat", "", ""))


def _strip_json_fence(value: str) -> str:
    text = value.strip()
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _normalize_llm_tag_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(tag).strip().lower() for tag in value if str(tag).strip()]


def _parse_llm_tags_answer(answer: object) -> LlmTagSuggestions:
    if isinstance(answer, str):
        answer = json.loads(_strip_json_fence(answer))
    if not isinstance(answer, dict):
        return LlmTagSuggestions([], [])

    genres = list(dict.fromkeys(_normalize_llm_tag_list(answer.get("genres"))))
    tags = list(dict.fromkeys(_normalize_llm_tag_list(answer.get("tags"))))
    return LlmTagSuggestions(genres, tags)


def get_llm_tag_suggestions(artist: str, title: str) -> LlmTagSuggestions:
    """Get structured music tag suggestions from configured LLM service."""
    if not cfg.tags.llm_url:
        return LlmTagSuggestions([], [])
    try:
        message = f"{artist} - {title}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "message": message,
            "thread_id": "vault_kimp3",
            "user": "kimp3",
            "location": "Undefined",
            "additional_instructions": "",
            "agent": "music_machine",
            "source": "kimp3",
            "actor_type": "program",
            "request_id": f"req_kimp3_{uuid4().hex}",
            "stream": False,
            "include_reasoning": False,
            "follow_up": False,
            "metadata": {
                "turn_id": f"turn_kimp3_{uuid4().hex}",
                "ephemeral": True,
                "skip_memory": True,
                "client_id": "kimp3",
            },
        }

        log.debug(f"Requesting LLM tags for: {message}")
        response = requests.post(
            _llm_chat_url(cfg.tags.llm_url),
            headers=headers,
            json=payload,
            timeout=cfg.tags.llm_timeout,
        )
        if response.status_code != 200:
            error_code = "unknown_error"
            error_message = ""
            try:
                error = response.json().get("detail", {}).get("error", {})
                error_code = error.get("code", error_code)
                error_message = error.get("message", "")
            except (json.JSONDecodeError, AttributeError):
                pass
            log.warning(
                f"LLM service returned HTTP {response.status_code}: {error_code} {error_message}".strip()
            )
            return LlmTagSuggestions([], [])

        response_data = response.json()
        if response_data.get("status") == "ignored":
            return LlmTagSuggestions([], [])
        answer = response_data.get("answer")
        if not answer:
            log.warning("LLM service returned empty tags")
            return LlmTagSuggestions([], [])

        suggestions = _parse_llm_tags_answer(answer)
        if not suggestions.genres and not suggestions.tags:
            log.warning("LLM service returned no parseable tags")
            return LlmTagSuggestions([], [])
        log.debug(f"LLM tags received: {suggestions}")
        return suggestions
    except requests.exceptions.RequestException as exc:
        log.error(f"Failed to connect to LLM service: {exc}")
        return LlmTagSuggestions([], [])
    except json.JSONDecodeError as exc:
        log.error(f"Failed to parse LLM response: {exc}")
        return LlmTagSuggestions([], [])
    except Exception as exc:
        log.error(f"Unexpected error getting LLM tags: {exc}")
        return LlmTagSuggestions([], [])


def get_llm_tags(artist: str, title: str) -> List[str]:
    """Get flattened music tags from configured LLM service."""
    suggestions = get_llm_tag_suggestions(artist, title)
    tags: dict[str, None] = {}
    for tag in suggestions.genres:
        tags.setdefault(tag, None)
    for tag in suggestions.tags:
        tags.setdefault(tag, None)
    return list(tags)

from __future__ import annotations

import json
import logging
import re
from typing import List, Tuple

import pylast
import requests

from kimp3.config import APP_NAME, cfg


NUMBER_OF_TAGS = 15
TAG_MIN_WEIGHT = 10

log = logging.getLogger(f"{APP_NAME}.{__name__}")


def _split_existing(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return [item.strip().lower() for item in value if item.strip()]
    return [item.strip().lower() for item in re.split("[,/]", value) if item.strip()]


def process_lastfm_tags(
    artist_tags: List[pylast.TopItem],
    album_tags: List[pylast.TopItem],
    track_tags: List[pylast.TopItem],
    existing_genre: str | list[str] = "",
    existing_tags: str | list[str] = "",
    artist_name: str = "",
    track_title: str = "",
    num: int = NUMBER_OF_TAGS,
) -> Tuple[str, str]:
    """Process Last.FM tags into genre and auxiliary tag strings."""
    tags_set = set()

    if cfg.tags.use_llm:
        tags_set.update(get_llm_tags(artist_name, track_title))

    for tags in [track_tags, album_tags, artist_tags]:
        for tag_obj in tags[0:min(num, len(tags) - 1)]:
            tag = tag_obj.item.get_name().lower()
            if tag in {artist_name.lower(), track_title.lower()}:
                continue
            tags_set.add(tag)

    if existing_tags:
        tags_set.update(_split_existing(existing_tags))
    if existing_genre:
        tags_set.update(_split_existing(existing_genre))

    result_genre = set()
    result_tags = set()
    for tag in tags_set:
        if not tag or len(tag) > cfg.tags.max_length:
            continue

        for similar_tags in cfg.tags.similar_tags:
            if tag in similar_tags:
                tag = similar_tags[0]
                break

        for pattern_list in cfg.tags.similar_tags_patterns:
            if any(re.match(pattern, tag) for pattern in pattern_list[1:]):
                tag = pattern_list[0]
                break

        if tag in cfg.tags.banned_tags:
            continue
        if any(re.match(pattern, tag) for pattern in cfg.tags.banned_tags_patterns):
            continue
        if tag in cfg.tags.banned_artists_from_tags:
            if artist_name.lower() in cfg.tags.banned_artists_from_tags[tag]:
                continue

        if tag in cfg.tags.genres:
            result_genre.add(tag)
        else:
            result_tags.add(tag)

    return ", ".join(sorted(result_genre)), ", ".join(sorted(result_tags))


def tags_list_to_str_list(tags: List[pylast.TopItem]) -> List[str]:
    return [tag.item.get_name() for tag in tags]


def get_llm_tags(artist: str, title: str) -> List[str]:
    """Get music tags from configured LLM service."""
    if not cfg.tags.llm_url:
        return []
    try:
        message = f"{artist} - {title}"
        headers = {"Content-Type": "application/json"}
        payload = {"thread_id": "vault_kimp3", "message": message}

        log.debug(f"Requesting LLM tags for: {message}")
        response = requests.get(cfg.tags.llm_url, headers=headers, params=payload, timeout=10)
        if response.status_code != 200:
            log.warning(f"LLM service returned HTTP {response.status_code}")
            return []

        response_data = response.json()
        tags_string = response_data.get("answer")
        if not tags_string:
            log.warning("LLM service returned empty tags")
            return []

        tags = [tag.strip().lower() for tag in tags_string.split(",") if tag.strip()]
        log.debug(f"LLM tags received: {tags}")
        return tags
    except requests.exceptions.RequestException as exc:
        log.error(f"Failed to connect to LLM service: {exc}")
        return []
    except json.JSONDecodeError as exc:
        log.error(f"Failed to parse LLM response: {exc}")
        return []
    except Exception as exc:
        log.error(f"Unexpected error getting LLM tags: {exc}")
        return []

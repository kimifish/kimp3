from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

from kimp3 import __version__
from kimp3.config import APP_NAME, cfg
from kimp3.strings_operations import split_album_title, string_similarity

log = logging.getLogger(f"{APP_NAME}.{__name__}")

BASE_URL = "https://musicbrainz.org/ws/2"
REQUEST_INTERVAL_SECONDS = 1.0
MUSICBRAINZ_ERRORS = (httpx.HTTPError, ValueError, KeyError, TypeError)

_request_lock = threading.Lock()
_last_request_at = 0.0
_artist_mbid_cache: dict[str, str | None] = {}
_artist_albums_cache: dict[tuple[str, str], list[AlbumCandidate]] = {}


@dataclass(frozen=True)
class AlbumCandidate:
    title: str
    track_count: int | None = None
    release_date: str | None = None
    source: str = "musicbrainz"


def _user_agent() -> str:
    return f"{APP_NAME}/{__version__} ({cfg.tags.musicbrainz_contact})"


def _get_json(path: str, params: dict[str, str | int]) -> dict[str, Any]:
    global _last_request_at

    with _request_lock:
        elapsed = time.monotonic() - _last_request_at
        if elapsed < REQUEST_INTERVAL_SECONDS:
            time.sleep(REQUEST_INTERVAL_SECONDS - elapsed)

        response = httpx.get(
            f"{BASE_URL}/{path}",
            params={**params, "fmt": "json"},
            headers={"Accept": "application/json", "User-Agent": _user_agent()},
            timeout=20.0,
        )
        _last_request_at = time.monotonic()

    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("MusicBrainz returned a non-object response")
    return data


def _find_artist_mbid(artist_name: str) -> str | None:
    if artist_name in _artist_mbid_cache:
        return _artist_mbid_cache[artist_name]

    try:
        data = _get_json(
            "artist",
            {"query": f'artist:"{artist_name}"', "limit": 5},
        )
    except MUSICBRAINZ_ERRORS as error:
        log.warning(
            f"`network,tags`MusicBrainz: Failed to find artist - {artist_name}: {error}"
        )
        _artist_mbid_cache[artist_name] = None
        return None

    best_mbid = None
    best_score = 0.0
    for artist in data.get("artists", []):
        name = str(artist.get("name") or "")
        score = (
            1.0
            if name.casefold() == artist_name.casefold()
            else string_similarity(name, artist_name, min_ratio=0.7)
        )
        if score > best_score:
            best_score = score
            best_mbid = str(artist.get("id") or "") or None

    _artist_mbid_cache[artist_name] = best_mbid
    return best_mbid


def _append_unique_album(
    albums: list[AlbumCandidate], seen_titles: set[str], candidate: AlbumCandidate
) -> None:
    if not candidate.title or candidate.title.casefold() in seen_titles:
        return
    seen_titles.add(candidate.title.casefold())
    albums.append(candidate)


def _display_release_title(release: dict[str, Any], query_qualifier: str) -> str:
    title = str(release.get("title") or "").strip()
    disambiguation = str(release.get("disambiguation") or "").strip()
    if not title or not disambiguation:
        return title
    if not query_qualifier:
        return title
    if string_similarity(disambiguation, query_qualifier, min_ratio=0.65):
        return f"{title} ({query_qualifier})"
    return title


def _search_releases(artist_name: str, album_title: str) -> list[AlbumCandidate]:
    if not album_title:
        return []
    base_title, query_qualifier = split_album_title(album_title)
    try:
        data = _get_json(
            "release",
            {
                "query": f'artist:"{artist_name}" AND release:"{base_title}"',
                "limit": 10,
            },
        )
    except MUSICBRAINZ_ERRORS as error:
        log.warning(
            f"`network,tags`MusicBrainz: Failed to search album releases - {artist_name} - {album_title}: {error}"
        )
        return []

    albums: list[AlbumCandidate] = []
    seen_titles: set[str] = set()
    for release in data.get("releases", []):
        title = _display_release_title(release, query_qualifier)
        _append_unique_album(
            albums,
            seen_titles,
            AlbumCandidate(title=title, release_date=release.get("date") or None),
        )
    return albums


def get_artist_albums(
    artist_name: str, album_title: str | None = None
) -> list[AlbumCandidate]:
    cache_key = (artist_name, album_title or "")
    if cache_key in _artist_albums_cache:
        return _artist_albums_cache[cache_key]

    albums = _search_releases(artist_name, album_title or "")
    seen_titles = {album.title.casefold() for album in albums}

    artist_mbid = _find_artist_mbid(artist_name)
    if not artist_mbid:
        _artist_albums_cache[cache_key] = albums
        return albums

    try:
        data = _get_json(
            "release-group",
            {
                "artist": artist_mbid,
                "type": "album|ep",
                "limit": 100,
            },
        )
    except MUSICBRAINZ_ERRORS as error:
        log.warning(
            f"`network,tags`MusicBrainz: Failed to get artist albums - {artist_name}: {error}"
        )
        _artist_albums_cache[cache_key] = albums
        return albums

    for release_group in data.get("release-groups", []):
        title = str(release_group.get("title") or "").strip()
        _append_unique_album(
            albums,
            seen_titles,
            AlbumCandidate(
                title=title,
                release_date=release_group.get("first-release-date") or None,
            ),
        )

    _artist_albums_cache[cache_key] = albums
    return albums


def clear_cache() -> None:
    _artist_mbid_cache.clear()
    _artist_albums_cache.clear()


def get_cache_stats() -> dict[str, int]:
    return {
        "musicbrainz_artists": len(_artist_mbid_cache),
        "musicbrainz_artist_albums": len(_artist_albums_cache),
    }

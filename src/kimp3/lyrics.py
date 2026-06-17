from __future__ import annotations

import logging
import re
from typing import Optional

import requests

from kimp3.config import APP_NAME, cfg
from kimp3.strings_operations import string_similarity


log = logging.getLogger(f"{APP_NAME}.{__name__}")


def _clean_title_for_comparison(title: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", title).strip()


def _get_lyrics_from_genius(artist: str, title: str) -> Optional[str]:
    try:
        headers = {"Authorization": f"Bearer {cfg.tags.genius_token}"}
        clean_title = _clean_title_for_comparison(title)
        clean_artist = _clean_title_for_comparison(artist)

        for replace_list in cfg.tags.genius_replacements:
            if clean_artist.lower() == replace_list[0].lower():
                clean_artist = replace_list[1]
                break

        response = requests.get(
            "https://api.genius.com/search",
            headers=headers,
            params={"q": f"{clean_artist} {clean_title}"},
            timeout=10,
        )
        if response.status_code != 200:
            log.warning(f'Genius API search failed for "{clean_artist} - {clean_title}": HTTP {response.status_code}')
            return None

        hits = response.json()["response"]["hits"]
        best_match = None
        for hit in hits:
            hit_title = _clean_title_for_comparison(hit["result"]["title"])
            hit_artist = _clean_title_for_comparison(hit["result"]["primary_artist"]["name"])
            if string_similarity(clean_title, hit_title, min_ratio=0.8) and string_similarity(
                clean_artist, hit_artist, min_ratio=0.6
            ):
                best_match = hit
                break

        if not best_match:
            return None

        page_response = requests.get(best_match["result"]["url"], timeout=10)
        if page_response.status_code != 200:
            return None

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(page_response.text, "html.parser")
        lyrics_containers = soup.find_all("div", attrs={"data-lyrics-container": "true"})
        if not lyrics_containers:
            return None

        lyrics = ""
        for container in lyrics_containers:
            for elem in container.stripped_strings:
                lyrics += elem + "\n"
        return lyrics.strip()
    except Exception as exc:
        log.error(f'Error fetching lyrics from Genius for "{artist} - {title}": {exc}')
        return None


def get_lyrics(artist: str, title: str) -> Optional[str]:
    """Get lyrics from Lyrics.ovh API or Genius fallback."""
    if not cfg.tags.fetch_lyrics:
        return None

    try:
        artist_clean = artist.replace("/", "_").replace("?", "_")
        title_clean = title.replace("/", "_").replace("?", "_")
        response = requests.get(f"https://api.lyrics.ovh/v1/{artist_clean}/{title_clean}", timeout=10)

        if response.status_code == 200:
            lyrics = response.json().get("lyrics")
            if lyrics:
                return lyrics

        lyrics = _get_lyrics_from_genius(artist, title)
        if lyrics:
            return lyrics
        log.info(f'No lyrics found for "{artist} - {title}"')
        return None
    except Exception as exc:
        log.error(f'Error fetching lyrics for "{artist} - {title}": {exc}')
        return None

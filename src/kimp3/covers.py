from __future__ import annotations

import hashlib
import io
import logging
from pathlib import Path
from typing import Optional, Tuple

import requests
from PIL import Image

from kimp3.config import APP_NAME, cfg


log = logging.getLogger(f"{APP_NAME}.{__name__}")
_album_cover_cache: dict[tuple[str, str], tuple[bytes, str]] = {}
_COVER_CACHE_DIR = Path(cfg.paths.cache_dir) / "album_covers"


def _get_cover_cache_path(artist: str, album: str) -> Path:
    cache_key = f"{artist}_{album}".encode("utf-8")
    return _COVER_CACHE_DIR / (hashlib.md5(cache_key).hexdigest() + ".jpg")


def get_album_cover(artist: str, album: str, size: str = "mega") -> Tuple[Optional[bytes], str]:
    """Get album cover from Last.FM or cache."""
    import kimp3.lastfm as lastfm

    cache_key = (artist, album)
    if cache_key in _album_cover_cache:
        return _album_cover_cache[cache_key]

    cache_path = _get_cover_cache_path(artist, album)
    if cache_path.exists():
        try:
            image_data = cache_path.read_bytes()
            result = (image_data, "image/jpeg")
            _album_cover_cache[cache_key] = result
            return result
        except OSError as exc:
            log.warning(f"Failed to read cached cover for {artist} - {album}: {exc}")

    try:
        album_obj = lastfm.network.get_album(artist, album)
        size_mapping = {"small": 0, "medium": 1, "large": 2, "extralarge": 3, "mega": 4}
        cover_url = album_obj.get_cover_image(size=size_mapping.get(size, 4))
        if not cover_url:
            log.info(f"No cover found for {artist} - {album}")
            return None, ""

        response = requests.get(cover_url, timeout=10)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content))
        output = io.BytesIO()
        image.convert("RGB").save(output, format="JPEG", quality=85, optimize=True)
        image_data = output.getvalue()

        result = (image_data, "image/jpeg")
        _album_cover_cache[cache_key] = result
        _COVER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(image_data)
        return result
    except Exception as exc:
        log.error(f"Failed to get cover for {artist} - {album}: {exc}")
        return None, ""


def clear_cover_cache() -> None:
    _album_cover_cache.clear()
    if _COVER_CACHE_DIR.exists():
        for file in _COVER_CACHE_DIR.iterdir():
            try:
                file.unlink()
            except OSError as exc:
                log.warning(f"Failed to delete cache file {file}: {exc}")


def cover_cache_size() -> int:
    return len(_album_cover_cache)

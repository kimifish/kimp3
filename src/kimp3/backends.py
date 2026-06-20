from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC, Picture
from mutagen.id3 import (
    APIC,
    COMM,
    ID3,
    TALB,
    TCON,
    TDRC,
    TIT2,
    TPE1,
    TPE2,
    TPOS,
    TRCK,
    USLT,
)

from kimp3.config import APP_NAME
from kimp3.models import Artwork, AudioTags, Lyrics

LYRICS_LOOKUP_COMMENT_DESC = "KiMP3 lyrics lookup"
LYRICS_LOOKUP_VORBIS_KEY = "kimp3:lyrics_lookup"
MANAGED_TAG_FIELDS = [
    "title",
    "artist",
    "album",
    "album_artist",
    "track_number",
    "total_tracks",
    "disc_number",
    "total_discs",
    "year",
    "genres",
    "lastfm_tags",
    "comment",
    "compilation",
    "rating",
    "artwork",
    "lyrics",
    "lyrics_lookup",
]


log = logging.getLogger(f"{APP_NAME}.{__name__}")


@dataclass(frozen=True)
class TagWritePolicy:
    """Controls which managed optional fields are written."""

    manage_artwork: bool = True
    manage_lyrics: bool = True


class TagBackend(Protocol):
    supported_extensions: set[str]

    def read(self, path: Path) -> AudioTags: ...

    def write(self, path: Path, tags: AudioTags, policy: TagWritePolicy) -> None: ...

    def verify(self, path: Path, expected: AudioTags, policy: TagWritePolicy) -> list[str]: ...


def _format_number(number: int | None, total: int | None, width: int) -> str | None:
    if number is None and total is None:
        return None
    if number is None:
        return f"/{total}"
    value = str(number).zfill(width)
    return f"{value}/{total}" if total else value


def _first(value: list[str] | None) -> str:
    return value[0] if value else ""


def _tag_value(tags: AudioTags, field: str) -> Any:
    value = getattr(tags, field)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


def _format_tag_value(value: Any) -> str:
    rendered = repr(value)
    if len(rendered) > 240:
        return f"{rendered[:237]}..."
    return rendered


def _set_id3_text_frame(
    id3: ID3, frame_id: str, frame_type: type, value: str | list[str] | None
) -> None:
    id3.delall(frame_id)
    if value:
        id3.add(frame_type(encoding=3, text=value))


def _verify_managed_tags(path: Path, expected: AudioTags, actual: AudioTags) -> list[str]:
    errors = []
    for field in MANAGED_TAG_FIELDS:
        expected_value = _tag_value(expected, field)
        actual_value = _tag_value(actual, field)
        if expected_value != actual_value:
            errors.append(
                f"Tag verification failed for {path}: {field} expected="
                f"{_format_tag_value(expected_value)} actual={_format_tag_value(actual_value)}"
            )
    return errors


class Mp3Id3Backend:
    supported_extensions = {".mp3"}

    def read(self, path: Path) -> AudioTags:
        id3 = ID3(path, v2_version=4)
        easy_tags = EasyID3(path)
        return AudioTags.from_mutagen(easy_tags, id3)

    def write(self, path: Path, tags: AudioTags, policy: TagWritePolicy) -> None:
        id3 = ID3(path)
        track_number = _format_number(
            tags.track_number,
            tags.total_tracks,
            len(str(tags.total_tracks)) if tags.total_tracks else 2,
        )
        disc_number = _format_number(
            tags.disc_number,
            tags.total_discs,
            len(str(tags.total_discs)) if tags.total_discs else 1,
        )

        _set_id3_text_frame(id3, "TIT2", TIT2, tags.title)
        _set_id3_text_frame(id3, "TPE1", TPE1, tags.artist)
        _set_id3_text_frame(id3, "TALB", TALB, tags.album)
        _set_id3_text_frame(id3, "TPE2", TPE2, tags.album_artist)
        _set_id3_text_frame(id3, "TCON", TCON, tags.genres)
        _set_id3_text_frame(id3, "TDRC", TDRC, str(tags.year) if tags.year else None)
        _set_id3_text_frame(id3, "TRCK", TRCK, track_number)
        _set_id3_text_frame(id3, "TPOS", TPOS, disc_number)

        comments_to_remove = ["", "Rating", "LastFM tags", LYRICS_LOOKUP_COMMENT_DESC]
        for key in list(id3.keys()):
            if key.startswith("COMM:"):
                desc = key.split(":")[1] if ":" in key else ""
                if desc in comments_to_remove:
                    del id3[key]
        if tags.comment:
            id3.add(COMM(encoding=3, lang="eng", desc="", text=tags.comment))
        if tags.rating is not None:
            id3.add(COMM(encoding=3, lang="eng", desc="Rating", text=f"Rating: {tags.rating}"))
        if tags.lastfm_tags:
            id3.add(COMM(encoding=3, lang="eng", desc="LastFM tags", text=f"LastFM tags: {tags.lastfm_tags_text}"))
        if tags.lyrics_lookup:
            id3.add(
                COMM(
                    encoding=3,
                    lang="eng",
                    desc=LYRICS_LOOKUP_COMMENT_DESC,
                    text=tags.lyrics_lookup.model_dump_json(),
                )
            )

        if policy.manage_artwork:
            for key in list(id3.keys()):
                if key.startswith("APIC:"):
                    del id3[key]
            if tags.artwork:
                id3.add(APIC(encoding=3, mime=tags.artwork.mime, type=3, desc="Cover", data=tags.artwork.data))
        if policy.manage_lyrics:
            for key in list(id3.keys()):
                if key.startswith("USLT:"):
                    del id3[key]
            if tags.lyrics:
                id3.add(USLT(encoding=3, lang=tags.lyrics.language, desc=tags.lyrics.description, text=tags.lyrics.text))
        id3.save(v2_version=3)

    def verify(self, path: Path, expected: AudioTags, policy: TagWritePolicy) -> list[str]:
        actual = self.read(path)
        return _verify_managed_tags(path, expected, actual)


class FlacVorbisBackend:
    supported_extensions = {".flac"}

    def read(self, path: Path) -> AudioTags:
        flac = FLAC(path)
        pictures = flac.pictures
        artwork = Artwork(data=pictures[0].data, mime=pictures[0].mime) if pictures else None
        lyrics_text = _first(flac.get("lyrics"))
        return AudioTags(
            title=_first(flac.get("title")),
            artist=_first(flac.get("artist")),
            album=_first(flac.get("album")),
            album_artist=_first(flac.get("albumartist")) or _first(flac.get("album artist")),
            track_number=AudioTags._parse_track_number(_first(flac.get("tracknumber")))[0],
            total_tracks=AudioTags._parse_track_number(_first(flac.get("tracknumber")))[1] or AudioTags._parse_track_number(_first(flac.get("tracktotal")))[0],
            disc_number=AudioTags._parse_track_number(_first(flac.get("discnumber")))[0],
            total_discs=AudioTags._parse_track_number(_first(flac.get("discnumber")))[1] or AudioTags._parse_track_number(_first(flac.get("disctotal")))[0],
            year=AudioTags._parse_year(_first(flac.get("date"))),
            genres=flac.get("genre", []),
            lastfm_tags=flac.get("kimp3:lastfm_tags", []),
            comment=_first(flac.get("comment")),
            compilation=AudioTags._parse_bool(_first(flac.get("compilation"))),
            rating=_first(flac.get("rating")),
            artwork=artwork,
            lyrics=Lyrics(text=lyrics_text) if lyrics_text else None,
            lyrics_lookup=_first(flac.get(LYRICS_LOOKUP_VORBIS_KEY)) or None,
        )

    def write(self, path: Path, tags: AudioTags, policy: TagWritePolicy) -> None:
        flac = FLAC(path)
        mapping = {
            "title": [tags.title] if tags.title else [],
            "artist": [tags.artist] if tags.artist else [],
            "album": [tags.album] if tags.album else [],
            "albumartist": [tags.album_artist] if tags.album_artist else [],
            "genre": tags.genres,
            "date": [str(tags.year)] if tags.year else [],
            "tracknumber": [_format_number(tags.track_number, None, 2)] if tags.track_number else [],
            "tracktotal": [str(tags.total_tracks)] if tags.total_tracks else [],
            "discnumber": [_format_number(tags.disc_number, None, 1)] if tags.disc_number else [],
            "disctotal": [str(tags.total_discs)] if tags.total_discs else [],
            "comment": [tags.comment] if tags.comment else [],
            "compilation": ["1"] if tags.compilation else [],
            "rating": [str(tags.rating)] if tags.rating is not None else [],
            "kimp3:lastfm_tags": tags.lastfm_tags,
            LYRICS_LOOKUP_VORBIS_KEY: [tags.lyrics_lookup.model_dump_json()] if tags.lyrics_lookup else [],
        }
        for key, value in mapping.items():
            if value:
                flac[key] = [item for item in value if item]
            elif key in flac:
                del flac[key]
        if policy.manage_lyrics:
            if tags.lyrics:
                flac["lyrics"] = [tags.lyrics.text]
            elif "lyrics" in flac:
                del flac["lyrics"]
        if policy.manage_artwork and tags.artwork:
            flac.clear_pictures()
            picture = Picture()
            picture.type = 3
            picture.mime = tags.artwork.mime
            picture.desc = "Cover"
            picture.data = tags.artwork.data
            flac.add_picture(picture)
        flac.save()

    def verify(self, path: Path, expected: AudioTags, policy: TagWritePolicy) -> list[str]:
        actual = self.read(path)
        return _verify_managed_tags(path, expected, actual)


BACKENDS: list[TagBackend] = [Mp3Id3Backend(), FlacVorbisBackend()]


def get_backend(path: Path) -> TagBackend:
    suffix = path.suffix.lower()
    for backend in BACKENDS:
        if suffix in backend.supported_extensions:
            return backend
    raise ValueError(f"Unsupported audio backend for {suffix}: {path}")

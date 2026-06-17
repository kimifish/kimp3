from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, COMM, ID3, USLT

from kimp3.config import APP_NAME
from kimp3.models import AudioTags, Artwork, Lyrics


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
    if number is None:
        return None
    value = str(number).zfill(width)
    return f"{value}/{total}" if total else value


def _first(value: list[str] | None) -> str:
    return value[0] if value else ""


class Mp3Id3Backend:
    supported_extensions = {".mp3"}

    def read(self, path: Path) -> AudioTags:
        id3 = ID3(path, v2_version=4)
        easy_tags = EasyID3(path)
        return AudioTags.from_mutagen(easy_tags, id3)

    def write(self, path: Path, tags: AudioTags, policy: TagWritePolicy) -> None:
        easy_tags = EasyID3(path)
        track_number = _format_number(tags.track_number, tags.total_tracks, len(str(tags.total_tracks)) if tags.total_tracks else 2)
        disc_number = _format_number(tags.disc_number, tags.total_discs, len(str(tags.total_discs)) if tags.total_discs else 1)
        tag_mapping = {
            "title": tags.title,
            "artist": tags.artist,
            "album": tags.album,
            "albumartist": tags.album_artist,
            "genre": tags.genre,
            "date": str(tags.year) if tags.year else None,
            "discnumber": disc_number,
            "tracknumber": track_number,
        }
        for key, value in tag_mapping.items():
            if value:
                easy_tags[key] = [value]
            elif key in easy_tags:
                del easy_tags[key]
        easy_tags.save()

        id3 = ID3(path)
        comments_to_remove = []
        if tags.comment:
            comments_to_remove.append("")
        if tags.rating is not None:
            comments_to_remove.append("Rating")
        if tags.lastfm_tags:
            comments_to_remove.append("LastFM tags")
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

        if policy.manage_artwork and tags.artwork:
            for key in list(id3.keys()):
                if key.startswith("APIC:"):
                    del id3[key]
            id3.add(APIC(encoding=3, mime=tags.artwork.mime, type=3, desc="Cover", data=tags.artwork.data))
        if policy.manage_lyrics and tags.lyrics:
            for key in list(id3.keys()):
                if key.startswith("USLT:"):
                    del id3[key]
            id3.add(USLT(encoding=3, lang=tags.lyrics.language, desc=tags.lyrics.description, text=tags.lyrics.text))
        id3.save(v2_version=3)

    def verify(self, path: Path, expected: AudioTags, policy: TagWritePolicy) -> list[str]:
        actual = self.read(path)
        return [] if expected.managed_equals(actual) else [f"Tag verification failed for {path}"]


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
            "tracknumber": [_format_number(tags.track_number, tags.total_tracks, 2)] if tags.track_number else [],
            "discnumber": [_format_number(tags.disc_number, tags.total_discs, 1)] if tags.disc_number else [],
            "comment": [tags.comment] if tags.comment else [],
            "compilation": ["1"] if tags.compilation else [],
            "rating": [str(tags.rating)] if tags.rating is not None else [],
            "kimp3:lastfm_tags": tags.lastfm_tags,
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
        return [] if expected.managed_equals(actual) else [f"Tag verification failed for {path}"]


BACKENDS: list[TagBackend] = [Mp3Id3Backend(), FlacVorbisBackend()]


def get_backend(path: Path) -> TagBackend:
    suffix = path.suffix.lower()
    for backend in BACKENDS:
        if suffix in backend.supported_extensions:
            return backend
    raise ValueError(f"Unsupported audio backend for {suffix}: {path}")

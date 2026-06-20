from __future__ import annotations

import logging
from datetime import date
from hashlib import sha256
from typing import Dict, List, Optional, Tuple

import pylast
from rich.pretty import pretty_repr

from kimp3.config import APP_NAME, cfg
from kimp3.covers import clear_cover_cache, cover_cache_size, get_album_cover
from kimp3.lyrics import get_lyrics
from kimp3.models import AbstractSongDir, AudioTags, LyricsLookup
from kimp3.strings_operations import string_similarity
from kimp3.tag_processing import NUMBER_OF_TAGS, TAG_MIN_WEIGHT, process_lastfm_tags

log = logging.getLogger(f"{APP_NAME}.{__name__}")
network: pylast.LastFMNetwork
LASTFM_ERRORS = (pylast.WSError, pylast.PyLastError)

_artist_corrections: Dict[str, str] = {}
_album_corrections: Dict[Tuple[str, str], str] = {}
_artist_albums_cache: Dict[str, List[pylast.TopItem]] = {}
_album_tracks_cache: Dict[Tuple[str, str], List[pylast.Track]] = {}
_genre_cache: Dict[Tuple[str, str], str] = {}
_artist_tags_cache: Dict[str, List[pylast.TopItem]] = {}
_album_tags_cache: Dict[Tuple[str, str], List[pylast.TopItem]] = {}


def _lyrics_retry_days(artist: str, title: str) -> int:
    jitter_days = max(0, cfg.tags.lyrics_not_found_retry_jitter_days)
    if jitter_days == 0:
        return max(1, cfg.tags.lyrics_not_found_retry_days)
    digest = sha256(f"{artist}\0{title}".encode("utf-8")).digest()
    jitter = int.from_bytes(digest[:2], "big") % (jitter_days + 1)
    return max(1, cfg.tags.lyrics_not_found_retry_days + jitter)


def _lyrics_lookup_is_fresh(lookup: LyricsLookup | None, artist: str, title: str) -> bool:
    if not lookup or lookup.status != "not_found":
        return False
    if lookup.artist and lookup.artist != artist:
        return False
    if lookup.title and lookup.title != title:
        return False
    return (date.today() - lookup.checked_at).days < _lyrics_retry_days(artist, title)


class TaggedTrack:
    def __init__(self, tags: AudioTags, songdir: AbstractSongDir):
        self.tags = tags
        self.songdir = songdir

        self.artist: pylast.Artist = network.get_artist(tags.artist)
        self.artist.name = self._correct_artist_name(self.artist)

        self.track: pylast.Track = network.get_track(
            self.artist.name or tags.artist, tags.title
        )
        self.track.title = self._correct_track_title(self.track)

        self.album: pylast.Album = network.get_album(
            self.artist.name or tags.artist, tags.album
        )
        self.album_artist: pylast.Artist = network.get_artist(
            tags.album_artist or tags.artist
        )
        self.track_number: Optional[int] = tags.track_number
        self.total_tracks: Optional[int] = tags.total_tracks
        self.disc_number: Optional[int] = tags.disc_number
        self.total_discs: Optional[int] = tags.total_discs
        self.year: Optional[int] = tags.year
        self.update_album_data()

        self.genres: list[str] = list(tags.genres)
        self.lastfm_tags: list[str] = list(tags.lastfm_tags)
        self.update_tags()

        self.rating: str = tags.rating
        self.lyrics: Optional[str] = tags.lyrics_text
        if cfg.tags.fetch_lyrics:
            self.update_lyrics()
        if cfg.tags.fetch_album_cover:
            self.update_cover()

    def __repr__(self) -> str:
        track_info = {
            "artist": self.artist.name if self.artist else None,
            "album": self.album.title if self.album else None,
            "album_artist": self.album_artist.name if self.album_artist else None,
            "title": self.track.title if self.track else None,
            "track": (
                f"{self.track_number}/{self.total_tracks}"
                if self.track_number
                else None
            ),
            "disc": (
                f"{self.disc_number}/{self.total_discs}" if self.disc_number else None
            ),
            "year": self.year if self.year else None,
            "genre": self.genres if self.genres else None,
            "lastfm_tags": self.lastfm_tags if self.lastfm_tags else None,
            "rating": self.rating if self.rating else None,
        }
        return pretty_repr(
            {key: value for key, value in track_info.items() if value is not None}
        )

    def _correct_artist_name(self, artist: pylast.Artist) -> Optional[str]:
        if not artist or not artist.name:
            log.warning(f"`network,tags`Artist doesn't exist - {artist}")
            return None
        if artist.name in _artist_corrections:
            return _artist_corrections[artist.name]
        try:
            corrected: str = artist.get_correction() or artist.name
            _artist_corrections[artist.name] = corrected
            artist.name = corrected
        except LASTFM_ERRORS:
            log.warning(f"`network,tags`Last.FM: Artist not found - {artist.name}")
            _artist_corrections[artist.name] = artist.name
        return artist.name

    def _correct_album_name(self, album: pylast.Album) -> Optional[str]:
        if not album or not album.title or not album.artist or not album.artist.name:
            log.warning(f"`network,tags`Album doesn't have enough data - {album}")
            return None

        cache_key = (album.artist.name, album.title)
        if cache_key in _album_corrections:
            return _album_corrections[cache_key]

        try:
            top_albums = _get_artist_albums(album.artist.name)
            corrected = self.tags.album
            best_ratio = 0.0
            best_album = None

            for iter_album in top_albums:
                current_ratio = string_similarity(
                    iter_album.item.title, self.tags.album
                )
                if current_ratio > best_ratio:
                    best_ratio = current_ratio
                    corrected = iter_album.item.title
                    best_album = iter_album.item

            if best_album and self.songdir.track_count:
                try:
                    lastfm_track_count = len(list(best_album.get_tracks()))
                    if lastfm_track_count != self.songdir.track_count:
                        log.warning(f"`network,tags`Track count mismatch for '{best_album.title}':")
                        log.warning(
                            f"`network,tags`Local: {self.songdir.track_count}, Last.FM: {lastfm_track_count}"
                        )
                except LASTFM_ERRORS:
                    log.warning(
                        f"`network,tags`Failed to get track count for album '{best_album.title}'"
                    )

            _album_corrections[cache_key] = corrected
            album.title = corrected
        except LASTFM_ERRORS:
            log.warning(
                f"`network,tags`Last.FM: Album not found - {self.tags.artist} - {self.tags.album}"
            )
            _album_corrections[cache_key] = album.title
        return album.title

    def _correct_track_title(self, track: pylast.Track) -> str:
        try:
            title = track.get_correction() or track.title
            if title == self.artist.name and title != self.tags.title:
                title = self.tags.title
        except LASTFM_ERRORS:
            log.warning(
                f"`network,tags`Last.FM: Track not found - {self.artist.name} - {self.tags.title}"
            )
            title = self.tags.title
        return title

    def update_album_data(self) -> None:
        self.album_artist.name = self._correct_artist_name(self.album_artist)
        self.album.title = self._correct_album_name(self.album)

        tracks = _get_album_tracks(self.album)
        if not tracks:
            return
        self.total_tracks = len(tracks)
        try:
            self.track_number = tracks.index(self.track) + 1
        except ValueError:
            pass

    def update_tags(self) -> None:
        if cfg.tags.skip_existing_tags and self.tags.genre and self.tags.lastfm_tags:
            log.debug(
                f"`tags`Skipping tags fetch for {self.artist.name} - {self.album.title} (tags already exist)"
            )
            return

        artist_tags = _get_tags(self.artist, min_weight=50)
        album_tags = _get_tags(self.album, min_weight=10)
        track_tags = _get_tags(self.track, min_weight=5)
        self.genres, self.lastfm_tags = process_lastfm_tags(
            artist_tags,
            album_tags,
            track_tags,
            existing_genre=self.genres,
            existing_tags=self.lastfm_tags,
            artist_name=self.artist.name or self.tags.artist,
            track_title=self.track.title or self.tags.title,
        )

    def update_cover(self) -> None:
        if cfg.tags.skip_existing_cover and self.tags.album_cover:
            log.debug(
                f"`tags`Skipping cover fetch for {self.artist.name} - {self.album.title} (cover already exists)"
            )
            return
        cover_data, mime_type = get_album_cover(
            self.artist.name or self.tags.artist, self.album.title or self.tags.album
        )
        if cover_data:
            self.tags.album_cover = cover_data
            self.tags.album_cover_mime = mime_type

    def update_lyrics(self) -> None:
        if cfg.tags.skip_existing_lyrics and self.tags.lyrics:
            log.debug(
                f"`tags`Skipping lyrics fetch for {self.artist.name} - {self.track.title} (lyrics already exist)"
            )
            self.lyrics = self.tags.lyrics_text
            self.tags.lyrics_lookup = None
            return
        artist = self.artist.name or self.tags.artist
        title = self.track.title or self.tags.title
        if _lyrics_lookup_is_fresh(self.tags.lyrics_lookup, artist, title):
            log.debug(f'`tags`Skipping lyrics fetch for "{artist} - {title}" (recent not_found marker exists)')
            return
        lyrics = get_lyrics(artist, title)
        if lyrics:
            self.lyrics = lyrics
            self.tags.lyrics_lookup = None
        else:
            self.tags.lyrics_lookup = LyricsLookup(checked_at=date.today(), artist=artist, title=title)

    def get_audiotags(self) -> AudioTags:
        return AudioTags(
            title=self.track.title or self.tags.title,
            artist=self.artist.name or self.tags.artist,
            album=self.album.title or self.tags.album,
            album_artist=self.album_artist.name or self.tags.album_artist,
            track_number=self.track_number or self.tags.track_number,
            total_tracks=self.total_tracks or self.tags.total_tracks,
            disc_number=self.disc_number or self.tags.disc_number,
            total_discs=self.total_discs or self.tags.total_discs,
            year=self.year or self.tags.year,
            genres=self.genres,
            lastfm_tags=self.lastfm_tags,
            rating=self.rating,
            album_cover=self.tags.album_cover,
            album_cover_mime=self.tags.album_cover_mime,
            lyrics=self.lyrics,
            lyrics_lookup=None if self.lyrics else self.tags.lyrics_lookup,
        )


def init_lastfm() -> None:
    global network
    try:
        network = pylast.LastFMNetwork(
            api_key=cfg.tags.lastfm_api_key,
            api_secret=cfg.tags.lastfm_api_secret,
            username=cfg.tags.lastfm_username,
            password_hash=cfg.tags.lastfm_password_hash,
        )
    except LASTFM_ERRORS as exc:
        log.warning(
            f"`network,tags`Last.FM authenticated login failed, continuing without session: {exc}"
        )
        network = pylast.LastFMNetwork(
            api_key=cfg.tags.lastfm_api_key,
            api_secret=cfg.tags.lastfm_api_secret,
        )
    log.info("`network,tags`Last.FM login")


def _get_album_tracks(album: pylast.Album) -> List[pylast.Track]:
    if not album or not album.title or not album.artist or not album.artist.name:
        log.warning(f"`network,tags`Album doesn't have enough data - {album}")
        return []
    cache_key = (album.artist.name, album.title)
    if cache_key in _album_tracks_cache:
        return _album_tracks_cache[cache_key]
    try:
        tracks = list(album.get_tracks())
        _album_tracks_cache[cache_key] = tracks
        return tracks
    except LASTFM_ERRORS:
        log.warning(
            f"`network,tags`Last.FM: Failed to get album tracks - {album.artist.name} - {album.title}"
        )
        return []


def _get_artist_albums(artist_name: str) -> List[pylast.TopItem]:
    if artist_name in _artist_albums_cache:
        return _artist_albums_cache[artist_name]
    try:
        top_albums = list(network.get_artist(artist_name).get_top_albums())
        _artist_albums_cache[artist_name] = top_albums
        return top_albums
    except LASTFM_ERRORS:
        log.warning(f"`network,tags`Last.FM: Failed to get artist albums - {artist_name}")
        return []


def _get_tags(
    obj: pylast.Album | pylast.Artist | pylast.Track, min_weight: int = TAG_MIN_WEIGHT
) -> List[pylast.TopItem]:
    cache_key = None
    cache = None
    if isinstance(obj, pylast.Artist):
        cache_key = obj.name
        cache = _artist_tags_cache
    elif isinstance(obj, pylast.Album) and obj.artist and obj.title:
        cache_key = (obj.artist.name, obj.title)
        cache = _album_tags_cache

    if cache_key is not None and cache is not None and cache_key in cache:
        return cache[cache_key]  # type: ignore[index]

    try:
        lastfm_raw_tags = obj.get_top_tags()
    except LASTFM_ERRORS:
        log.warning("`network,tags`Last.FM: Failed to get tags")
        return []

    lastfm_tags = []
    for tag_obj in lastfm_raw_tags:
        if int(tag_obj.weight) < min_weight:
            continue
        if len(tag_obj.item.get_name()) > 50:
            continue
        lastfm_tags.append(tag_obj)

    result = lastfm_tags[0 : NUMBER_OF_TAGS * 2]
    if cache is not None and cache_key is not None:
        cache[cache_key] = result  # type: ignore[index]
    return result


def get_genre(tags: AudioTags) -> str:
    cache_key = (tags.album_artist, tags.album)
    if cache_key in _genre_cache:
        return _genre_cache[cache_key]
    try:
        album = network.get_album(tags.album_artist, tags.album)
        artist = network.get_artist(tags.artist)
        names = [tag.item.get_name() for tag in _get_tags(album) + _get_tags(artist)]
        genre = ", ".join(dict.fromkeys(names[:5])).title()
        _genre_cache[cache_key] = genre
        return genre
    except LASTFM_ERRORS:
        log.warning(f"`network,tags`Last.FM: Failed to get genre for {tags.artist} - {tags.album}")
        _genre_cache[cache_key] = ""
        return ""


def clear_cache() -> None:
    _artist_corrections.clear()
    _album_corrections.clear()
    _genre_cache.clear()
    _artist_albums_cache.clear()
    _album_tracks_cache.clear()
    _artist_tags_cache.clear()
    _album_tags_cache.clear()
    clear_cover_cache()
    log.debug("`state`All Last.FM caches cleared")


def get_cache_stats() -> Dict[str, int]:
    return {
        "artists": len(_artist_corrections),
        "albums": len(_album_corrections),
        "genres": len(_genre_cache),
        "artist_albums": len(_artist_albums_cache),
        "album_tracks": len(_album_tracks_cache),
        "artist_tags": len(_artist_tags_cache),
        "album_tags": len(_album_tags_cache),
        "album_covers": cover_cache_size(),
    }

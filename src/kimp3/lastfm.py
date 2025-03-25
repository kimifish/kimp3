#  -*- coding: utf-8 -*-
# pyright: basic
# pyright: reportAttributeAccessIssue=false

import logging
import re
from typing import List, Optional, Dict, Tuple, Set
from operator import attrgetter
from unittest import result
import pylast
from config import cfg, APP_NAME
from models import AudioTags
from rich.pretty import pretty_repr
from difflib import SequenceMatcher

NUMBER_OF_TAGS = 15
TAG_MIN_WEIGHT = 10

log = logging.getLogger(f"{APP_NAME}.{__name__}")

network: pylast.LastFMNetwork

# Кэши для хранения исправлений
_artist_corrections: Dict[str, str] = {}
_album_corrections: Dict[Tuple[str, str], str] = {}  # (artist, album) -> corrected_album
_artist_albums_cache: Dict[str, List[pylast.TopItem]] = {}  # artist -> albums
_album_tracks_cache: Dict[Tuple[str, str], List[pylast.Track]] = {}  # (artist, album) -> tracks
_genre_cache: Dict[Tuple[str, str], str] = {}  # (artist, album) -> genre
_artist_tags_cache: Dict[str, str] = {}  # (artist, album, track) -> tags
_album_tags_cache: Dict[Tuple[str, str], str] = {}  # (artist, album, track) -> tags

class TaggedTrack():
    def __init__(self, tags: AudioTags):
        self.tags = tags

        self.artist: pylast.Artist = network.get_artist(tags.artist)
        self.artist.name = self._correct_artist_name(self.artist)

        self.track: pylast.Track = network.get_track(self.artist.name or tags.artist, tags.title)
        self.track.title = self._correct_track_title(self.track)

        self.album: pylast.Album = network.get_album(self.artist.name or tags.artist, tags.album)
        self.album_artist: pylast.Artist = network.get_artist(tags.album_artist or tags.artist)
        self.track_number: Optional[int] = tags.track_number
        self.total_tracks: Optional[int] = tags.total_tracks
        self.disc_number: Optional[int] = tags.disc_number
        self.total_discs: Optional[int] = tags.total_discs
        self.year: Optional[str] = tags.year
        self.update_album_data()

        self.genre: str = tags.genre
        self.lastfm_tags: str = tags.lastfm_tags
        self.update_tags()

        self.rating: str = tags.rating

        log.debug(self)

    def __repr__(self) -> str:
        track_info = {
            "artist": self.artist.name if self.artist else None,
            "album": self.album.title if self.album else None,
            "album_artist": self.album_artist.name if self.album_artist else None,
            "title": self.track.title if self.track else None,
            "track": f"{self.track_number}/{self.total_tracks}" if self.track_number else None,
            "disc": f"{self.disc_number}/{self.total_discs}" if self.disc_number else None,
            "year": self.year if self.year else None,
            "genre": self.genre if self.genre else None,
            "lastfm_tags": self.lastfm_tags if self.lastfm_tags else None,
            "rating": self.rating if self.rating else None,
        }
        
        # Remove None values for cleaner output
        track_info = {k: v for k, v in track_info.items() if v is not None}
        
        return pretty_repr(track_info)

    def _correct_artist_name(self, artist: pylast.Artist) -> Optional[str]:
        """Получает корректное имя исполнителя из Last.FM или кэша."""
        
        if not artist or not artist.name:
            log.warning(f'Artist doesn\'t exist - {artist}')
            return None

        # Проверяем кэш
        if artist.name in _artist_corrections:
            return _artist_corrections[artist.name]
            
        try:
            corrected: str = artist.get_correction() or artist.name
            
            # Сохраняем в кэш
            _artist_corrections[artist.name] = corrected
            artist.name = corrected
        except pylast.WSError:
            log.warning(f'Last.FM: Artist not found - {self.artist.name}')
            # Кэшируем отсутствие исправлений
            _artist_corrections[artist.name] = artist.name
        finally:
            return artist.name

    def _correct_album_name(self, album: pylast.Album) -> Optional[str]:
        """Получает корректное название альбома из Last.FM или кэша."""
        if not album or not album.title or not album.artist or not album.artist.name:
            log.warning(f'Album doesn\'t have enough data - {album}')
            return None

        cache_key = (album.artist.name, album.title)
        
        # Проверяем кэш
        if cache_key in _album_corrections:
            return _album_corrections[cache_key]
            
        try:
            top_albums = _get_artist_albums(album.artist.name)
            corrected = self.tags.album

            for iter_album in top_albums:
                if string_similarity(iter_album.item.title, self.tags.album):
                    corrected = iter_album.item.title
                    break
            
            # Сохраняем в кэш
            _album_corrections[cache_key] = corrected
            album.title = corrected
        except pylast.WSError:
            log.warning(f'Last.FM: Album not found - {self.tags.artist} - {self.tags.album}')
            # Кэшируем отсутствие исправлений
            _album_corrections[cache_key] = album.title
        finally:
            return album.title

    def _correct_track_title(self, track: pylast.Track):
        """Получает корректное название трека из Last.FM."""
        try:
            title = track.get_correction() or track.title
            # Если исправление совпадает с исполнителем, то это не исправление
            if title == self.artist.name and title != self.tags.title:
                title = self.tags.title
        except pylast.WSError:
            log.warning(f'Last.FM: Track not found - {self.artist.name} - {self.tags.title}')
            title = self.tags.title
        finally:
            return title

    def update_album_data(self):
        self.album_artist.name = self._correct_artist_name(self.album_artist)
        self.album.title = self._correct_album_name(self.album)

        tracks = _get_album_tracks(self.album)
        if not tracks:
            return
        self.total_tracks = str(len(tracks))
        try:
            self.track_number = str(tracks.index(self.track) + 1)
        except ValueError:
            pass
    
    def update_tags(self):
        artist_tags = _get_tags(self.artist, min_weight=50)
        album_tags = _get_tags(self.album, min_weight=10)
        track_tags = _get_tags(self.track, min_weight=5)
        self.genre, self.lastfm_tags = process_lastfm_tags(
            artist_tags, album_tags, track_tags, 
            existing_genre=self.genre,
            existing_tags=self.lastfm_tags,
            artist_name=self.artist.name or self.tags.artist,
            track_title=self.track.title or self.tags.title,
            )

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
            genre=self.genre,
            lastfm_tags=self.lastfm_tags,
            rating=self.rating
        )

def init_lastfm():
    """Инициализация подключения к Last.FM."""
    global network
    network = pylast.LastFMNetwork(api_key=cfg.lastfm.api_key,
                                api_secret=cfg.lastfm.api_secret,
                                username=cfg.lastfm.username,
                                password_hash=cfg.lastfm.password_hash)
    log.info('Last.FM login')


def _get_album_tracks(album: pylast.Album) -> List[pylast.Track]:
    if not album or not album.title or not album.artist or not album.artist.name:
        log.warning(f'Album doesn\'t have enough data - {album}')
        return []

    cache_key = (album.artist.name, album.title)
    
    # Проверяем кэш
    if cache_key in _album_tracks_cache:
        return _album_tracks_cache[cache_key]

    try:
        tracks = list(album.get_tracks())
        _album_tracks_cache[cache_key] = tracks
        return tracks
    except pylast.WSError:
        log.warning(f'Last.FM: Failed to get album tracks - {album.artist.name} - {album.title}')
        return []


def _get_artist_albums(artist_name: str) -> List[pylast.TopItem]:
    if artist_name in _artist_albums_cache:
        return _artist_albums_cache[artist_name]

    try:
        top_albums = list(network.get_artist(artist_name).get_top_albums())
        _artist_albums_cache[artist_name] = top_albums
        return top_albums
    except pylast.WSError:
        log.warning(f'Last.FM: Failed to get artist albums - {artist_name}')
        return []


def _get_tags(
    obj: pylast.Album | pylast.Artist | pylast.Track, 
    min_weight: int = TAG_MIN_WEIGHT,
    ) -> List[pylast.TopItem]:
    """Получает теги объекта Last.FM."""

    global _artist_tags_cache
    global _album_tags_cache

    cache_key, cache = None, None

    if isinstance(obj, pylast.Artist):
        cache_key = obj.name
        cache = _artist_tags_cache
    elif isinstance(obj, pylast.Album):
        if obj.artist and obj.title:
            cache_key = (obj.artist.name, obj.title)
            cache = _album_tags_cache

    if cache_key is not None and cache is not None and cache_key in cache:
        if cache:
            return cache[cache_key]  # type: ignore

    try:
        lastfm_raw_tags = obj.get_top_tags()
    except pylast.WSError:
        log.warning('Last.FM: Failed to get tags')
        return list()

    lastfm_tags = list()
    for tag_obj in lastfm_raw_tags:
        if int(tag_obj.weight) < min_weight:
            continue
        lastfm_tags.append(tag_obj)

    if cache is not None:
        cache[cache_key] = lastfm_tags[0:NUMBER_OF_TAGS*2]  # type: ignore
    return lastfm_tags[0:NUMBER_OF_TAGS*2]


def get_genre(tags: AudioTags) -> str:
    """Получает жанры на основе тегов альбома и исполнителя."""
    cache_key = (tags.album_artist, tags.album)
    
    # Проверяем кэш
    if cache_key in _genre_cache:
        return _genre_cache[cache_key]
        
    try:
        album = network.get_album(tags.album_artist, tags.album)
        artist = network.get_artist(tags.artist)
        
        genre_tags = _get_tags(album)
        artist_tags = _get_tags(artist)
        
        # Объединяем теги альбома и исполнителя
        all_tags = genre_tags.copy()
        for tag in artist_tags:
            if tag not in all_tags:
                all_tags.append(tag)

        if len(all_tags) > 5:
            all_tags = all_tags[0:4]
            
        genre = ", ".join(all_tags).title()  # type: ignore
        
        # Сохраняем в кэш
        _genre_cache[cache_key] = genre
        return genre
    except pylast.WSError:
        log.warning(f'Last.FM: Failed to get genre for {tags.artist} - {tags.album}')
        # Кэшируем пустой результат
        _genre_cache[cache_key] = ""
        return ""


def clear_cache() -> None:
    """Очищает все кэши исправлений."""
    global _artist_corrections, _album_corrections, _genre_cache
    _artist_corrections.clear()
    _album_corrections.clear()
    _genre_cache.clear()
    log.debug("Last.FM correction caches cleared")


def get_cache_stats() -> Dict[str, int]:
    """Возвращает статистику использования кэшей."""
    return {
        "artists": len(_artist_corrections),
        "albums": len(_album_corrections),
        "genres": len(_genre_cache)
    }


def process_lastfm_tags(
    artist_tags: List[pylast.TopItem],
    album_tags: List[pylast.TopItem],
    track_tags: List[pylast.TopItem],
    existing_genre: str = "",
    existing_tags: str = "",
    artist_name: str = "",
    track_title: str = "",
    num: int = NUMBER_OF_TAGS, 
    ) -> Tuple[str, str]:
    """Обрабатывает теги из Last.FM."""

    tags_set = set()
    for tags in [track_tags, album_tags, artist_tags]:
        # for tag_obj in sorted(tags, key=attrgetter('weight'), reverse=True)[0:min(num, len(tags) - 1)]:
        # log.debug(pretty_repr(tags_list_to_str_list(tags)))
        for tag_obj in tags[0:min(num, len(tags) - 1)]:
                
            tag = tag_obj.item.get_name().lower()

            if tag == artist_name.lower():
                continue
            if tag == track_title.lower():
                continue
            tags_set.add(tag)

    tags_set.update(item.strip().lower() for item in re.split('[,/]', existing_tags))
    tags_set.update(item.strip().lower() for item in re.split('[,/]', existing_genre))
    log.debug(pretty_repr(tags_set))

    result_genre = set()
    result_tags = set()
    for tag in tags_set:

        if not tag:
            continue

        # Проверяем схожие теги и используем основной тег из группы
        for similar_tags in cfg.lastfm.similar_tags:
            # similar_tags = list(similar_tags)
            if tag in similar_tags:
                tag = similar_tags[0]
                break

        for pattern_list in cfg.lastfm.similar_tags_patterns:
            if any(re.match(pattern, tag) for pattern in pattern_list[1:]):
                tag = pattern_list[0]
                break

        if tag in cfg.lastfm.banned_tags:
            continue

        if any(re.match(pattern, tag) for pattern in cfg.lastfm.banned_tags_patterns):
            continue

        if tag in cfg.lastfm.banned_artists_from_tags.__dict__:
            if artist_name.lower() in cfg.lastfm.banned_artists_from_tags.__dict__[tag]:
                continue

        if tag in cfg.lastfm.genres:
            result_genre.add(tag)
            continue
        result_tags.add(tag)

    return ", ".join(result_genre), ", ".join(result_tags)


def normalize_string(s: str) -> str:
    return ''.join(c.lower() for c in s if c.isalnum())


def string_similarity(str1: str, str2: str, min_ratio: float = 0.8) -> bool:
    """
    Compare strings using SequenceMatcher.
    Returns True if similarity ratio >= min_ratio
    """
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio() >= min_ratio


def tags_list_to_str_list(tags: List[pylast.TopItem]) -> List[str]:
    return [tag.item.get_name() for tag in tags]
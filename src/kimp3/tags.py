#  -*- coding: utf-8 -*-
# pyright: basic
# pyright: reportAttributeAccessIssue=false

import logging
import re
from typing import List, Optional, Dict, Tuple, Set
import pylast
from rich.pretty import pretty_repr
import requests
from PIL import Image
import io
import hashlib
from pathlib import Path
import os
from kimp3.config import cfg, APP_NAME
from kimp3.interface.utils import yes_or_no
from kimp3.models import AudioTags
from kimp3.strings_operations import normalize_string, string_similarity

NUMBER_OF_TAGS = 15
TAG_MIN_WEIGHT = 10

log = logging.getLogger(f"{APP_NAME}.{__name__}")

network: pylast.LastFMNetwork

# Caches for storing corrections
_artist_corrections: Dict[str, str] = {}
_album_corrections: Dict[Tuple[str, str], str] = {}  # (artist, album) -> corrected_album
_artist_albums_cache: Dict[str, List[pylast.TopItem]] = {}  # artist -> albums
_album_tracks_cache: Dict[Tuple[str, str], List[pylast.Track]] = {}  # (artist, album) -> tracks
_genre_cache: Dict[Tuple[str, str], str] = {}  # (artist, album) -> genre
_artist_tags_cache: Dict[str, str] = {}  # (artist, album, track) -> tags
_album_tags_cache: Dict[Tuple[str, str], str] = {}  # (artist, album, track) -> tags
_album_cover_cache: Dict[Tuple[str, str], Tuple[bytes, str]] = {}  # (artist, album) -> (image_data, mime_type)
_COVER_CACHE_DIR = Path(cfg.paths.cache_dir) / "album_covers"


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
        self.year: Optional[int] = tags.year
        self.update_album_data()

        self.genre: str = tags.genre
        self.lastfm_tags: str = tags.lastfm_tags
        self.update_tags()

        self.rating: str = tags.rating
        self.lyrics: Optional[str] = tags.lyrics

        if cfg.tags.fetch_lyrics:
            self.update_lyrics()
        if cfg.tags.fetch_album_cover:
            self.update_cover()

        # log.debug(self)

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
        """Get corrected artist name from Last.FM or cache.
        
        Args:
            artist: Last.FM artist object
            
        Returns:
            Corrected artist name or None if artist doesn't exist
        """
        if not artist or not artist.name:
            log.warning(f'Artist doesn\'t exist - {artist}')
            return None

        # Check cache
        if artist.name in _artist_corrections:
            return _artist_corrections[artist.name]
            
        try:
            corrected: str = artist.get_correction() or artist.name
            
            # Save to cache
            _artist_corrections[artist.name] = corrected
            artist.name = corrected
        except pylast.WSError:
            log.warning(f'Last.FM: Artist not found - {self.artist.name}')
            # Cache the absence of corrections
            _artist_corrections[artist.name] = artist.name
        finally:
            return artist.name

    def _correct_album_name(self, album: pylast.Album) -> Optional[str]:
        """Gets corrected album name from Last.FM or cache."""
        if not album or not album.title or not album.artist or not album.artist.name:
            log.warning(f'Album doesn\'t have enough data - {album}')
            return None

        cache_key = (album.artist.name, album.title)
        
        # Check cache
        if cache_key in _album_corrections:
            return _album_corrections[cache_key]
            
        try:
            top_albums = _get_artist_albums(album.artist.name)
            corrected = self.tags.album

            for iter_album in top_albums:
                if string_similarity(iter_album.item.title, self.tags.album):
                    corrected = iter_album.item.title
                    break
            
            # Save to cache
            _album_corrections[cache_key] = corrected
            album.title = corrected
        except pylast.WSError:
            log.warning(f'Last.FM: Album not found - {self.tags.artist} - {self.tags.album}')
            # Cache the absence of corrections
            _album_corrections[cache_key] = album.title
        finally:
            return album.title

    def _correct_track_title(self, track: pylast.Track):
        """Get corrected track title from Last.FM.
        
        Args:
            track: Last.FM track object
            
        Returns:
            Corrected track title or original title if not found
        """
        try:
            title = track.get_correction() or track.title
            # If correction matches artist name and differs from current title,
            # keep the current title
            if title == self.artist.name and title != self.tags.title:
                title = self.tags.title
        except pylast.WSError:
            log.warning(f'Last.FM: Track not found - {self.artist.name} - {self.tags.title}')
            title = self.tags.title
        finally:
            return title

    def update_album_data(self):
        """Update album metadata including artist, title and track numbers."""
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
        """Update tags from Last.FM including genre and other metadata."""

        if cfg.tags.skip_existing_tags and self.tags.genre and self.tags.lastfm_tags:
            log.debug(f"Skipping tags fetch for {self.artist.name} - {self.album.title} (tags already exist)")
            return

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

    def update_cover(self):
        """Update album cover from Last.FM."""
        # Skip if cover already exists and skip_existing_cover is True
        if cfg.tags.skip_existing_cover and self.tags.album_cover:
            log.debug(f"Skipping cover fetch for {self.artist.name} - {self.album.title} (cover already exists)")
            return

        cover_data, mime_type = get_album_cover(
            self.artist.name or self.tags.artist,
            self.album.title or self.tags.album
        )
        if cover_data:
            self.tags.album_cover = cover_data
            self.tags.album_cover_mime = mime_type

    def update_lyrics(self):
        """Update track lyrics from Lyrics.ovh."""
        # Skip if lyrics already exist and skip_existing_lyrics is True
        if cfg.tags.skip_existing_lyrics and self.tags.lyrics:
            log.debug(f"Skipping lyrics fetch for {self.artist.name} - {self.track.title} (lyrics already exist)")
            self.lyrics = self.tags.lyrics
            return

        lyrics = get_lyrics(
            self.artist.name or self.tags.artist,
            self.track.title or self.tags.title
        )
        if lyrics:
            self.lyrics = lyrics

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
            rating=self.rating,
            album_cover=self.tags.album_cover,
            album_cover_mime=self.tags.album_cover_mime,
            lyrics=self.lyrics
        )


def init_lastfm():
    """Initialize Last.FM connection."""
    global network
    network = pylast.LastFMNetwork(api_key=cfg.tags.lastfm_api_key,
                                api_secret=cfg.tags.lastfm_api_secret,
                                username=cfg.tags.lastfm_username,
                                password_hash=cfg.tags.lastfm_password_hash)
    log.info('Last.FM login')


def _get_album_tracks(album: pylast.Album) -> List[pylast.Track]:
    if not album or not album.title or not album.artist or not album.artist.name:
        log.warning(f'Album doesn\'t have enough data - {album}')
        return []

    cache_key = (album.artist.name, album.title)
    
    # Check cache
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
    """Gets tags from Last.FM object."""

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
    """Gets genres based on album and artist tags."""
    cache_key = (tags.album_artist, tags.album)
    
    # Check cache
    if cache_key in _genre_cache:
        return _genre_cache[cache_key]
        
    try:
        album = network.get_album(tags.album_artist, tags.album)
        artist = network.get_artist(tags.artist)
        
        genre_tags = _get_tags(album)
        artist_tags = _get_tags(artist)
        
        # Combine album and artist tags
        all_tags = genre_tags.copy()
        for tag in artist_tags:
            if tag not in all_tags:
                all_tags.append(tag)

        if len(all_tags) > 5:
            all_tags = all_tags[0:4]
            
        genre = ", ".join(all_tags).title()  # type: ignore
        
        # Save to cache
        _genre_cache[cache_key] = genre
        return genre
    except pylast.WSError:
        log.warning(f'Last.FM: Failed to get genre for {tags.artist} - {tags.album}')
        # Cache empty result
        _genre_cache[cache_key] = ""
        return ""


def _get_cover_cache_path(artist: str, album: str) -> Path:
    """Generate a unique cache file path for album cover."""
    cache_key = f"{artist}_{album}".encode('utf-8')
    filename = hashlib.md5(cache_key).hexdigest() + ".jpg"
    return _COVER_CACHE_DIR / filename


def get_album_cover(artist: str, album: str, size: str = "mega") -> Tuple[Optional[bytes], str]:
    """Get album cover from Last.FM or cache.
    
    Args:
        artist: Artist name
        album: Album name
        size: Image size ('small', 'medium', 'large', 'extralarge', 'mega')
    
    Returns:
        Tuple of (image_data, mime_type) or (None, "") if not found
    """
    cache_key = (artist, album)
    
    # Check memory cache first
    if cache_key in _album_cover_cache:
        return _album_cover_cache[cache_key]
    
    # Check file cache
    cache_path = _get_cover_cache_path(artist, album)
    if cache_path.exists():
        try:
            with open(cache_path, 'rb') as f:
                image_data = f.read()
                result = (image_data, "image/jpeg")
                _album_cover_cache[cache_key] = result
                return result
        except Exception as e:
            log.warning(f"Failed to read cached cover for {artist} - {album}: {e}")
    
    try:
        # Get album info from Last.FM
        album_obj = network.get_album(artist, album)
        # Convert size string to pylast size constant
        size_mapping = {
            'small': 0,
            'medium': 1,
            'large': 2,
            'extralarge': 3,
            'mega': 4
        }
        cover_url = album_obj.get_cover_image(size=size_mapping.get(size, 4))  # Default to mega if invalid size
        
        if not cover_url:
            log.info(f"No cover found for {artist} - {album}")
            return None, ""
        
        # Download image
        response = requests.get(cover_url, timeout=10)
        response.raise_for_status()
        
        # Process image
        image = Image.open(io.BytesIO(response.content))
        
        # Convert to JPEG and optimize
        output = io.BytesIO()
        image.convert('RGB').save(output, format='JPEG', quality=85, optimize=True)
        image_data = output.getvalue()
        
        # Cache result
        result = (image_data, "image/jpeg")
        _album_cover_cache[cache_key] = result
        
        # Save to file cache
        os.makedirs(_COVER_CACHE_DIR, exist_ok=True)
        with open(cache_path, 'wb') as f:
            f.write(image_data)
        
        return result
        
    except Exception as e:
        log.error(f"Failed to get cover for {artist} - {album}: {e}")
        return None, ""


def _clean_title_for_comparison(title: str) -> str:
    """Remove translations and notes in parentheses from title.
    
    Args:
        title: Original title
        
    Returns:
        Cleaned title
    """
    # Remove everything in parentheses
    import re
    cleaned = re.sub(r'\s*\([^)]*\)', '', title)
    return cleaned.strip()


def _get_lyrics_from_genius(artist: str, title: str) -> Optional[str]:
    """Get lyrics using Genius API.
    
    Args:
        artist: Artist name
        title: Track title
    
    Returns:
        Lyrics text or None if not found
    """
    try:
        # Search for the song
        headers = {'Authorization': f'Bearer {cfg.tags.genius_token}'}
        search_url = 'https://api.genius.com/search'
        # Clean input titles

        clean_title = _clean_title_for_comparison(title)
        clean_artist = _clean_title_for_comparison(artist)

        for replace_list in cfg.tags.genius_replacements:
            if clean_artist.lower() == replace_list[0].lower():
                clean_artist = replace_list[1]
                break
            
        params = {'q': f'{clean_artist} {clean_title}'}
        
        response = requests.get(search_url, headers=headers, params=params, timeout=10)
        if response.status_code != 200:
            log.warning(f"Genius API search failed for \"{clean_artist} - {clean_title}\": HTTP {response.status_code}")
            return None
            
        data = response.json()
        hits = data['response']['hits']
        
        if not hits:
            return None
            
        # Find the best matching hit
        best_match = None
        for hit in hits:
            hit_title = _clean_title_for_comparison(hit['result']['title'])
            hit_artist = _clean_title_for_comparison(hit['result']['primary_artist']['name'])
            
            # Check both title and artist similarity
            log.debug(f"[bold cyan]Matching lyrics:[/] [yellow]{hit_title}[/] vs [green]{clean_title}[/] "
                     f"by [yellow]{hit_artist}[/] vs [green]{clean_artist}[/]")
            if (string_similarity(clean_title, hit_title, min_ratio=0.8) and 
                string_similarity(clean_artist, hit_artist, min_ratio=0.6)):
                best_match = hit
                break
        
        if not best_match:
            log.debug(f"No matching lyrics found on Genius for \"{artist} - {title}\"")
            return None
            
        # Get lyrics URL from the best match
        song_url = best_match['result']['url']
        
        # Fetch the page and extract lyrics
        response = requests.get(song_url, timeout=10)
        if response.status_code != 200:
            return None
            
        # Use BeautifulSoup to parse the HTML and extract lyrics
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        lyrics_containers = soup.find_all('div', attrs={'data-lyrics-container': 'true'})
        if not lyrics_containers:
            return None
            
        # Combine text from all containers
        lyrics = ''
        for container in lyrics_containers:
            # Extract text, keeping line breaks
            for elem in container.stripped_strings:
                lyrics += elem + '\n'
        
        return lyrics.strip()
        
    except Exception as e:
        log.error(f"Error fetching lyrics from Genius for \"{artist} - {title}\": {e}")
        return None


def get_lyrics(artist: str, title: str) -> Optional[str]:
    """Get lyrics from Lyrics.ovh API or Genius as fallback.
    
    Args:
        artist: Artist name
        title: Track title
    
    Returns:
        Lyrics text or None if not found
    """
    if not cfg.tags.fetch_lyrics:
        return None
        
    try:
        # Try Lyrics.ovh first
        artist_clean = artist.replace('/', '_').replace('?', '_')
        title_clean = title.replace('/', '_').replace('?', '_')
        
        url = f"https://api.lyrics.ovh/v1/{artist_clean}/{title_clean}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            lyrics = response.json().get('lyrics')
            if lyrics:
                return lyrics
                
        log.debug(f"No lyrics found on Lyrics.ovh for \"{artist} - {title}\", trying Genius...")
        
        # Try Genius as fallback
        lyrics = _get_lyrics_from_genius(artist, title)
        if lyrics:
            return lyrics
            
        log.info(f"No lyrics found for \"{artist} - {title}\" on either service")
        return None
            
    except Exception as e:
        log.error(f"Error fetching lyrics for \"{artist} - {title}\": {e}")
        return None


def clear_cache() -> None:
    """Clear all caches used for Last.FM data.
    
    Clears the following caches:
    - Artist corrections
    - Album corrections
    - Genre cache
    - Artist albums cache
    - Album tracks cache
    - Artist tags cache
    - Album tags cache
    - Album cover cache (both memory and disk)
    """
    global _artist_corrections, _album_corrections, _genre_cache
    global _artist_albums_cache, _album_tracks_cache
    global _artist_tags_cache, _album_tags_cache, _album_cover_cache

    _artist_corrections.clear()
    _album_corrections.clear()
    _genre_cache.clear()
    _artist_albums_cache.clear()
    _album_tracks_cache.clear()
    _artist_tags_cache.clear()
    _album_tags_cache.clear()
    _album_cover_cache.clear()

    # Clear disk cache for album covers
    if _COVER_CACHE_DIR.exists():
        for file in _COVER_CACHE_DIR.iterdir():
            try:
                file.unlink()
            except Exception as e:
                log.warning(f"Failed to delete cache file {file}: {e}")

    log.debug("All Last.FM caches cleared")


def get_cache_stats() -> Dict[str, int]:
    """Get statistics about cache usage.
    
    Returns:
        Dictionary containing counts for each cache:
        - artists: Number of artist corrections
        - albums: Number of album corrections
        - genres: Number of cached genres
        - artist_albums: Number of cached artist album lists
        - album_tracks: Number of cached album track lists
        - artist_tags: Number of cached artist tag lists
        - album_tags: Number of cached album tag lists
        - album_covers: Number of cached album covers
    """
    return {
        "artists": len(_artist_corrections),
        "albums": len(_album_corrections),
        "genres": len(_genre_cache),
        "artist_albums": len(_artist_albums_cache),
        "album_tracks": len(_album_tracks_cache),
        "artist_tags": len(_artist_tags_cache),
        "album_tags": len(_album_tags_cache),
        "album_covers": len(_album_cover_cache)
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
    """Processes tags from Last.FM."""

    tags_set = set()
    for tags in [track_tags, album_tags, artist_tags]:
        for tag_obj in tags[0:min(num, len(tags) - 1)]:
                
            tag = tag_obj.item.get_name().lower()

            if tag == artist_name.lower():
                continue
            if tag == track_title.lower():
                continue
            tags_set.add(tag)
    if existing_tags:
        tags_set.update(item.strip().lower() for item in re.split('[,/]', existing_tags))
    if existing_genre:
        tags_set.update(item.strip().lower() for item in re.split('[,/]', existing_genre))
    # log.debug(pretty_repr(tags_set))

    result_genre = set()
    result_tags = set()
    for tag in tags_set:

        if not tag:
            continue

        # Check similar tags and use the main tag from the group
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

        if tag in cfg.tags.banned_artists_from_tags.__dict__:
            if artist_name.lower() in cfg.tags.banned_artists_from_tags.__dict__[tag]:
                continue

        if tag in cfg.tags.genres:
            result_genre.add(tag)
            continue
        result_tags.add(tag)

    return ", ".join(result_genre), ", ".join(result_tags)


def tags_list_to_str_list(tags: List[pylast.TopItem]) -> List[str]:
    return [tag.item.get_name() for tag in tags]

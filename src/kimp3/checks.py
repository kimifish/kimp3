# -*- coding: utf-8 -*-
# pyright: basic
# pyright: reportAttributeAccessIssue=false

import logging

from kimp3.config import cfg, APP_NAME
log = logging.getLogger(f"{APP_NAME}.{__name__}")


def test_is_album(album):
    """Checks if the directory is an album.
    
    Simple check: all songs must have the same album tag.
    
    Args:
        album: SongDir object with audio files
        
    Returns:
        tuple[bool, str]: (is album, album title)
    """
    album_title_set = album.gather_tag_values('album')

    is_album = True
    album_title = ""

    if len(album_title_set) > 1:
        is_album = False
    else:
        album_title = album_title_set.pop()

    log.debug("Directory is album: " + str(is_album) + ", Album title: " + album_title)
    return is_album, album_title


def test_is_compilation(album) -> tuple[bool, str]:
    """Checks if the album is a compilation.
    
    An album is considered a compilation if no artist performs more than
    a certain proportion (compilation_coef) of all songs in the album.
    
    Args:
        album: SongDir object with audio files
        
    Returns:
        tuple[bool, str]: (is compilation, album artist name)
    """
    # Count songs for each artist
    artist_counts = {}
    total_tracks = len(album.audio_files)
    
    for track in album.audio_files:
        # Use album_artist if available, otherwise song_artist
        artist = track.tags.album_artist or track.tags.song_artist
        if not artist:
            continue
            
        artist_counts[artist] = artist_counts.get(artist, 0) + 1
    
    if not artist_counts:
        return True, "Various Artists"
    
    # Find artist with maximum number of songs
    max_artist = max(artist_counts.items(), key=lambda x: x[1])
    artist_name, track_count = max_artist
    
    # If main artist's song proportion is below threshold - it's a compilation
    is_compilation = (track_count / total_tracks) <= float(cfg.collection.compilation_coef)
    album_artist = "Various Artists" if is_compilation else artist_name
    
    log.debug(f"Album compilation check: {is_compilation=}, {album_artist=}, "
              f"max_artist_tracks={track_count}/{total_tracks}")
    
    return is_compilation, album_artist

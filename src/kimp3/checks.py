# -*- coding: utf-8 -*-
# pyright: basic
# pyright: reportAttributeAccessIssue=false

import logging

from kimp3.config import cfg, APP_NAME
log = logging.getLogger(f"{APP_NAME}.{__name__}")


def test_is_album(album):
    # Метод проверяет, является ли каталог альбомом или нет. Возвращает буль.
    # Проверка простая: у всех песен тэг альбома должен быть одинаковым.

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
    """Проверяет, является ли альбом сборником.
    
    Альбом считается сборником, если ни один исполнитель не исполняет больше
    определенной доли (compilation_coef) всех песен в альбоме.
    
    Args:
        album: Объект SongDir с аудио файлами
        
    Returns:
        tuple[bool, str]: (является ли сборником, имя исполнителя альбома)
    """
    # Подсчитываем количество песен для каждого исполнителя
    artist_counts = {}
    total_tracks = len(album.audio_files)
    
    for track in album.audio_files:
        # Используем album_artist если он есть, иначе song_artist
        artist = track.tags.album_artist or track.tags.song_artist
        if not artist:
            continue
            
        artist_counts[artist] = artist_counts.get(artist, 0) + 1
    
    if not artist_counts:
        return True, "Various Artists"
    
    # Находим исполнителя с максимальным количеством песен
    max_artist = max(artist_counts.items(), key=lambda x: x[1])
    artist_name, track_count = max_artist
    
    # Если доля песен главного исполнителя меньше порога - это сборник
    is_compilation = (track_count / total_tracks) <= float(cfg.collection.compilation_coef)
    album_artist = "Various Artists" if is_compilation else artist_name
    
    log.debug(f"Album compilation check: {is_compilation=}, {album_artist=}, "
              f"max_artist_tracks={track_count}/{total_tracks}")
    
    return is_compilation, album_artist

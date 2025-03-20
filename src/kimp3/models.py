#  -*- coding: utf-8 -*-
# pyright: basic
# pyright: reportAttributeAccessIssue=false

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict
from mutagen import File
from mutagen.id3 import ID3
from mutagen.easyid3 import EasyID3

class FileOperation(Enum):
    COPY = "copy"
    MOVE = "move"
    NONE = "none"

@dataclass
class AudioTags:
    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    track_number: Optional[int] = None
    total_tracks: Optional[int] = None
    disc_number: Optional[int] = None
    year: Optional[int] = None
    genre: Optional[str] = None
    tags: Optional[str] = None
    
    @classmethod
    def from_mutagen(cls, audio_file) -> "AudioTags":
        """
        Создает экземпляр AudioTags из mutagen.File объекта.
        
        Args:
            audio_file: mutagen.File объект
            
        Returns:
            AudioTags: новый экземпляр с данными из файла
        """
        if audio_file is None:
            return cls()
            
        # Пробуем получить теги в формате EasyID3
        try:
            if not isinstance(audio_file.tags, EasyID3):
                audio_file.add_tags(ID3=EasyID3)
            tags = audio_file.tags
        except Exception:
            return cls()

        # Извлекаем номер трека и общее количество треков
        track_info = tags.get('tracknumber', ['0/0'])[0].split('/')
        track_number = int(track_info[0]) if track_info[0].isdigit() else None
        total_tracks = int(track_info[1]) if len(track_info) > 1 and track_info[1].isdigit() else None

        # Извлекаем номер диска и общее количество дисков
        disc_info = tags.get('discnumber', ['0/0'])[0].split('/')
        disc_number = int(disc_info[0]) if disc_info[0].isdigit() else None

        # Извлекаем год
        date = tags.get('date', [''])[0]
        year = None
        if date:
            # Пробуем извлечь год из разных форматов даты
            try:
                # Формат YYYY
                if len(date) == 4 and date.isdigit():
                    year = int(date)
                # Формат YYYY-MM-DD
                elif '-' in date:
                    year = int(date.split('-')[0])
            except ValueError:
                pass

        return cls(
            title=tags.get('title', [''])[0],
            artist=tags.get('artist', [''])[0],
            album=tags.get('album', [''])[0],
            album_artist=tags.get('albumartist', [''])[0],
            track_number=track_number,
            total_tracks=total_tracks,
            disc_number=disc_number,
            year=year,
            genre=tags.get('genre', [''])[0]
        )

@dataclass
class AudioFile:
    path: Path
    tags: AudioTags
    new_path: Optional[Path] = None

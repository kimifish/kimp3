from enum import Enum
from dataclasses import dataclass
from pathlib import Path
from token import OP
from typing import Optional
import io

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3


class FileOperation(Enum):
    """Перечисление возможных операций с файлами.
    
    Attributes:
        COPY: Копирование файла
        MOVE: Перемещение файла
        NONE: Операция не выбрана/не требуется
    """
    COPY = "copy"
    MOVE = "move"
    NONE = "none"

    @classmethod
    def from_string(cls, value: str) -> 'FileOperation':
        """Создает FileOperation из строки.
        
        Args:
            value: Строковое значение операции ('copy', 'move' или 'none')
            
        Returns:
            Соответствующее значение FileOperation
            
        Raises:
            ValueError: Если передано неверное значение
        """
        try:
            return cls(value.lower())
        except ValueError:
            valid_values = [op.value for op in cls]
            raise ValueError(
                f"Invalid operation '{value}'. Must be one of: {', '.join(valid_values)}"
            )


@dataclass
class AudioTags:
    """Модель для хранения тегов аудио файла."""
    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    track_number: Optional[int] = None
    total_tracks: Optional[int] = None
    disc_number: Optional[int] = None
    total_discs: Optional[int] = None
    year: Optional[int] = None
    genre: str = ""
    lastfm_tags: str = ""
    comment: str = ""
    compilation: bool = False
    rating: str = ""
    album_cover: Optional[bytes] = None
    album_cover_mime: str = "image/jpeg"
    lyrics: Optional[str] = None  # Add lyrics field

    @classmethod
    def from_mutagen(cls, easy_tags: EasyID3, id3: ID3) -> 'AudioTags':
        """Создает объект AudioTags из EasyID3 и ID3."""
        def get_tag_value(key: str) -> str:
            try:
                return easy_tags.get(key, [''])[0]
            except (IndexError, KeyError):
                return ''

        def get_comment(desc: str) -> str:
            """Извлекает комментарий с определенным описанием."""
            for key, frame in id3.items():
                if key.startswith('COMM:') and frame.desc == desc:
                    return frame.text[0][len(desc + ': '):]
            return ''

        track_info = cls._parse_track_number(get_tag_value('tracknumber'))
        disc_info = cls._parse_track_number(get_tag_value('discnumber'))

        return cls(
            title=get_tag_value('title'),
            artist=get_tag_value('artist'),
            album=get_tag_value('album'),
            album_artist=get_tag_value('albumartist'),
            track_number=track_info[0],
            total_tracks=track_info[1],
            disc_number=disc_info[0],
            total_discs=disc_info[1],
            year=cls._parse_year(get_tag_value('date')),
            genre=get_tag_value('genre'),
            comment=get_tag_value('comment'),
            compilation=bool(get_tag_value('compilation')),
            lastfm_tags=get_comment('LastFM tags'),
            rating=get_comment('Rating')
        )

    @staticmethod
    def _parse_track_number(value: str) -> tuple[Optional[int], Optional[int]]:
        """Парсит строку с номером трека/диска в формате 'number/total'."""
        if not value:
            return None, None
        parts = value.split('/')
        try:
            number = int(parts[0]) if parts[0] else None
            total = int(parts[1]) if len(parts) > 1 and parts[1] else None
            return number, total
        except (ValueError, IndexError):
            return None, None

    @staticmethod
    def _parse_year(value: str) -> Optional[int]:
        """Извлекает год из строки даты."""
        if not value:
            return None
        try:
            # Берем первые 4 символа как год
            return int(value[:4])
        except (ValueError, IndexError):
            return None



@dataclass
class AudioFile:
    """Модель для хранения информации об аудио файле."""
    path: Path
    tags: AudioTags
    new_path: Optional[Path] = None


#!/usr/bin/python3
#  -*- coding: utf-8 -*-

import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from mutagen import File as MutaFile
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, COMM

import file_operations
import lastfm
from config import cfg, APP_NAME

log = logging.getLogger(f"{APP_NAME}.{__name__}")


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
    comment: str = ""
    compilation: bool = False
    lastfm_tags: str = ""  # Добавляем поле для lastfm тегов
    rating: str = ""       # Добавляем поле для рейтинга

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
                    return frame.text
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


class UsualFile:
    def __init__(self, filepath: str | Path):
        self.filepath = Path(filepath)
        log.debug(' + ' + str(self.filepath))
        self.path = self.filepath.parent
        self.name = self.filepath.name
        self.new_filepath: Path = Path()
        self.new_name: str = ''
        self.new_path: Path = Path()

    def print_changes(self) -> None:
        print(f"{self.filepath} ---> {self.new_filepath}")


class AudioFile(UsualFile):
    """
    Класс для работы с MP3-файлом, включая его теги и операции перемещения/копирования.
    """
    def __init__(self, filepath: str | Path, song_dir=None):
        super().__init__(filepath)
        self.genre_paths: List[Path] = []
        self.song_dir = song_dir
        self.tags = self._read_tags()
        self._calculate_new_paths()

    def _read_tags(self) -> AudioTags:
        """Читает теги из файла, используя mutagen."""
        try:
            # Открываем файл как EasyID3 для основных тегов
            easy_tags = EasyID3(self.filepath)
            
            # Открываем тот же файл как ID3 для доступа к комментариям
            id3 = ID3(self.filepath)
            
            # Создаем объект AudioTags из easy_tags
            tags = AudioTags.from_mutagen(easy_tags, id3)

            # Обработка артикля 'The' в имени исполнителя
            for field in ['artist', 'album_artist']:
                value = getattr(tags, field, '')
                if value.lower().startswith('the '):
                    if cfg.the_the == 'remove':
                        setattr(tags, field, value[4:])
                    elif cfg.the_the == 'move':
                        setattr(tags, field, value[4:] + ', the')

            # Обработка компиляций
            if self.song_dir and getattr(self.song_dir, 'is_compilation', False):
                if not tags.album_artist or tags.album_artist.lower() in cfg.bad_artists:
                    tags.album_artist = 'Various Artists'
                    tags.compilation = True

            # Проверка и исправление пустых значений
            if not tags.album_artist and tags.artist:
                tags.album_artist = tags.artist

            return tags

        except Exception as e:
            log.error(f"Error reading tags from {self.filepath}: {e}")
            return AudioTags()

    def write_tags(self) -> None:
        """Записывает теги в файл."""
        try:
            mutagen_file = MutaFile(self.filepath)
            if mutagen_file is None:
                log.error(f"Could not open file for writing: {self.filepath}")
                return

            # ... код обновления тегов ...

            mutagen_file.save()

        except Exception as e:
            log.error(f"Error writing tags to {self.filepath}: {e}")

    def _calculate_new_paths(self) -> Optional[Path]:
        """Вычисляет новый путь для файла на основе тегов и конфигурации."""
        try:
            base_dir = Path(cfg.collection.directory)
            
            genre_pattern = cfg.paths.patterns.genre

            if self.song_dir and self.song_dir.is_compilation:
                pattern = cfg.paths.patterns.compilation
            else:
                pattern = cfg.paths.patterns.album

            # Добавляем номер диска только если их больше одного
            if not self.tags.total_discs or self.tags.total_discs <= 1:
                pattern = pattern.replace(' (CD%disc_num)', '')
                genre_pattern = genre_pattern.replace(' (CD%disc_num)', '')

            # Словарь для сопоставления переменных паттерна с полями AudioTags
            tag_mapping = {
                'song_title': str(self.tags.title),
                'song_artist': str(self.tags.artist),
                'album_title': str(self.tags.album),
                'album_artist': str(self.tags.album_artist),
                'track_num': str(self.tags.track_number).zfill(2) if self.tags.track_number else 'XX',
                'num_of_tracks': str(self.tags.total_tracks) if self.tags.total_tracks else 'XX',
                'disc_num': str(self.tags.disc_number) if self.tags.disc_number else '1',
                'genre': str(self.tags.genre),
                'year': str(self.tags.year) if self.tags.year else 'XXXX'
            }

            # Замена шаблонных переменных реальными значениями
            path = pattern
            for var, value in tag_mapping.items():
                path = path.replace(f'%{var}', value or "Unknown")

            # Разделяем путь и создаем Path объект
            path_parts = [p for p in path.split('/') if p]
            new_path = base_dir.joinpath(*path_parts)
            
            # Создаем пути для жанров, используя паттерн из конфига
            if self.tags.genre:
                for genre in str(self.tags.genre).split(','):
                    genre_path = genre_pattern
                    tag_mapping['genre'] = genre.strip()
                    for var, value in tag_mapping.items():
                        genre_path = genre_path.replace(f'%{var}', value or "Unknown")
                    
                    genre_path_parts = [p for p in genre_path.split('/') if p]
                    full_genre_path = base_dir.joinpath(*genre_path_parts)
                    self.genre_paths.append(full_genre_path)

            self.new_filepath = new_path
            self.new_path = new_path.parent
            self.new_name = new_path.name

        except Exception as e:
            log.error(f"Error calculating new path for {self.filepath}: {e}")
            return None

    def copy_to(self) -> None:
        """Подготавливает файл к копированию."""
        self._calculate_new_paths()
        file_operations.files_to_copy.append(self)
        
        for genre_path in self.genre_paths:
            file_operations.files_to_create_link.append([str(self.new_filepath), str(genre_path)])

    def move_to(self) -> None:
        """Подготавливает файл к перемещению."""
        self._calculate_new_paths()
        file_operations.files_to_move.append(self)
        
        for genre_path in self.genre_paths:
            file_operations.files_to_create_link.append([str(self.new_filepath), str(genre_path)])

    def print_changes(self):
        for tag in self.tags.old:
            print("{}: {} ---> {}".format(tag, self.tags.old[tag], self.tags.new[tag]))
        super(AudioFile, self).print_changes()
        print("----------------------------------")

    def _printall(self):
        print(self.filepath)
        print()
        print('Artist: ' + self.tags.new['song_artist'])
        print('Title: ' + self.tags.new['song_title'])
        print('Album artist: ' + self.tags.new['album_artist'])
        print('Album title: ' + self.tags.new['album_title'])
        print('Genre: ' + self.tags.new['genre'])
        print('Year: ' + self.tags.new['year'])
        print('Track: ' + self.tags.new['track_num'] + "/" + self.tags.new['num_of_tracks'])

        # def __str__(self):
        #     print(self.tags[u'song_artist'] + u' — ' + self.tags[u'song_title'])

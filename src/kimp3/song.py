# -*- coding: utf-8 -*-
# pyright: basic
# pyright: reportAttributeAccessIssue=false

import logging
from pathlib import Path
from typing import Optional, List

from mutagen._file import File as MutaFile
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3

import file_operations
from models import AudioTags
from config import cfg, APP_NAME
import lastfm

log = logging.getLogger(f"{APP_NAME}.{__name__}")


class UsualFile:
    def __init__(self, filepath: str | Path, song_dir=None):
        self.filepath = Path(filepath)
        self.path = self.filepath.parent
        self.name = self.filepath.name
        self.new_filepath: Path = Path()
        self.new_name: str = ''
        self.new_path: Path = Path()
        self.song_dir = song_dir

    def print_changes(self) -> None:
        print(f"{self.filepath} ---> {self.new_filepath}")


class AudioFile(UsualFile):
    """
    Класс для работы с MP3-файлом, включая его теги и операции перемещения/копирования.
    """
    def __init__(self, filepath: str | Path, song_dir=None):
        super().__init__(filepath, song_dir)
        
        self.genre_paths: List[Path] = []
        self.tags = self._read_tags()

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

    def print_changes(self) -> None:
        """Выводит изменения в тегах и пути файла."""
        # Выводим изменения в тегах
        if self.tags.old != self.tags.new:
            print("\nTag changes:")
            for field in ['title', 'artist', 'album', 'album_artist', 
                         'genre', 'year', 'track_number', 'total_tracks', 
                         'disc_number', 'total_discs']:
                old_value = getattr(self.tags.old, field, '')
                new_value = getattr(self.tags.new, field, '')
                if old_value != new_value:
                    print(f"  {field}: {old_value or '<empty>'} → {new_value or '<empty>'}")
        
        # Выводим изменение пути файла
        if self.filepath != self.new_filepath:
            print("\nFile path change:")
            print(f"  {self.filepath}\n  → {self.new_filepath}")
        
        # Выводим информацию о символических ссылках для жанров
        if self.genre_paths:
            print("\nGenre symlinks will be created in:")
            for path in self.genre_paths:
                print(f"  {path}")
        
        print("\n" + "-" * 50)

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

    def check_tags(self) -> dict[str, tuple[str, str]]:
        """Проверяет и корректирует теги через Last.FM.
        
        Returns:
            Словарь изменений в формате {поле: (старое_значение, новое_значение)}
        """
        if not cfg.tags.check_tags:
            return {}

        changes = {}
        old_tags = AudioTags(
            title=self.tags.title,
            artist=self.tags.artist,
            album=self.tags.album,
            album_artist=self.tags.album_artist,
            genre=self.tags.genre
        )
        
        try:
            # Обновляем теги через Last.FM
            self.tags = lastfm.update_tags_from_lastfm(self.tags)
            
            # Собираем изменения
            for field in ['title', 'artist', 'album', 'album_artist', 'genre']:
                old_value = getattr(old_tags, field)
                new_value = getattr(self.tags, field)
                
                if old_value != new_value:
                    changes[field] = (old_value or '<empty>', new_value)
                    log.info(f"Tag '{field}' corrected from '{old_value}' to '{new_value}' "
                            f"for {self.filepath.name}")
        except Exception as e:
            log.error(f"Error checking tags for {self.filepath}: {e}")
        
        return changes

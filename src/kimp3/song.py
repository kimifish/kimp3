# -*- coding: utf-8 -*-
# pyright: basic
# pyright: reportAttributeAccessIssue=false

import logging
from pathlib import Path
from typing import Optional, List

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3
from mutagen.id3._frames import COMM, APIC, USLT

import kimp3.file_operations as file_operations
import kimp3.tags
from kimp3.models import AudioTags, FileOperation
from kimp3.config import cfg, APP_NAME
from kimp3.strings_operations import sanitize_path_component

log = logging.getLogger(f"{APP_NAME}.{__name__}")


class UsualFile:
    def __init__(self, filepath: str | Path, song_dir=None):
        self._filepath = Path(filepath)
        self.path = self._filepath.parent
        self.name = self._filepath.name
        self._new_filepath: Path = Path()
        self.new_name: str = ''
        self.new_path: Path = Path()
        self.song_dir = song_dir
        self.operation_processed = FileOperation.NONE

    @property
    def filepath(self) -> Path:
        return self._filepath

    @filepath.setter
    def filepath(self, value: str | Path) -> None:
        self._filepath = Path(value)
        self.path = self._filepath.parent
        self.name = self._filepath.name

    @property
    def new_filepath(self) -> Path:
        return self._new_filepath

    @new_filepath.setter
    def new_filepath(self, value: str | Path) -> None:
        self._new_filepath = Path(value)
        self.new_path = self._new_filepath.parent
        self.new_name = self._new_filepath.name

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
        self.old_tags = AudioTags()

    def _read_tags(self) -> AudioTags:
        """Читает теги из файла, используя mutagen."""
        try:
            # Открываем файл как EasyID3 для основных тегов
            easy_tags = EasyID3(self.filepath)
            
            # Открываем тот же файл как ID3 для доступа к комментариям и обложке
            id3 = ID3(self.filepath)
            
            # Получаем обложку альбома
            cover_data = None
            cover_mime = "image/jpeg"
            
            for key in id3.keys():
                if key.startswith('APIC:'):
                    cover = id3[key]
                    cover_data = cover.data
                    cover_mime = cover.mime
                    break
            
            # Создаем объект AudioTags из easy_tags
            tags = AudioTags.from_mutagen(easy_tags, id3)
            
            # Добавляем обложку
            tags.album_cover = cover_data
            tags.album_cover_mime = cover_mime

            # Читаем текст песни из USLT фрейма
            lyrics = None
            for key in id3.keys():
                if key.startswith('USLT:'):
                    lyrics = id3[key].text
                    break
            tags.lyrics = lyrics

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

    def fetch_tags(self) -> dict[str, tuple[str, str]]:
        """Проверяет и корректирует теги через Last.FM.
        
        Returns:
            Словарь изменений в формате {поле: (старое_значение, новое_значение)}
        """
        changes = {}
        self.old_tags = AudioTags(
            title=self.tags.title,
            artist=self.tags.artist,
            album=self.tags.album,
            album_artist=self.tags.album_artist,
            track_number=self.tags.track_number,
            total_tracks=self.tags.total_tracks,
            disc_number=self.tags.disc_number,
            total_discs=self.tags.total_discs,
            year=self.tags.year,
            lastfm_tags=self.tags.lastfm_tags,
            genre=self.tags.genre,
            comment=self.tags.comment,
            compilation=self.tags.compilation,
            rating=self.tags.rating
        )
        
        try:
            # Обновляем теги через Last.FM
            if cfg.tags.fetch_tags:
                self.tags = kimp3.tags.TaggedTrack(self.tags).get_audiotags()
            
            # Обработка артикля 'The' в имени исполнителя
            for field in ['artist', 'album_artist']:
                value = getattr(self.tags, field, '')
                if value.lower().startswith('the '):
                    if cfg.tags.the_the == 'remove':
                        setattr(self.tags, field, value[4:])
                    elif cfg.tags.the_the == 'move':
                        setattr(self.tags, field, value[4:] + ', the')

            # Собираем изменения
            for field in AudioTags.__annotations__:
                old_value = getattr(self.old_tags, field)
                new_value = getattr(self.tags, field)
                
                if old_value != new_value:
                    changes[field] = (old_value or '<empty>', new_value or '<empty>')
                    # log.info(f"Tag '{field}' corrected from '{old_value}' to '{new_value}' "
                            # f"for {self.filepath.name}")
        except Exception as e:
        # except NotImplementedError as e:
            log.error(f"Error fetching tags for {self.filepath}: {e}")
        
        return changes

    def write_tags(self) -> None:
        """Записывает теги в файл."""
        try:
            # Открываем файл как EasyID3 для основных тегов
            easy_tags = EasyID3(self.filepath)
            
            # Открываем тот же файл как ID3 для доступа к комментариям
            id3 = ID3(self.filepath)
            
            # Определяем количество цифр для номеров треков и дисков
            track_width = len(str(self.tags.total_tracks)) if self.tags.total_tracks else 2
            disc_width = len(str(self.tags.total_discs)) if self.tags.total_discs else 1
            
            # Форматируем номера с ведущими нулями и общим количеством
            track_number = None
            if self.tags.track_number:
                track_number = str(self.tags.track_number).zfill(track_width)
                if self.tags.total_tracks:
                    track_number = f"{track_number}/{self.tags.total_tracks}"

            disc_number = None
            if self.tags.disc_number:
                disc_number = str(self.tags.disc_number).zfill(disc_width)
                if self.tags.total_discs:
                    disc_number = f"{disc_number}/{self.tags.total_discs}"
            
            # Форматируем год
            year = str(self.tags.year) if self.tags.year else None

            # Словарь тегов для записи
            tag_mapping = {
                'title': self.tags.title,
                'artist': self.tags.artist,
                'album': self.tags.album,
                'albumartist': self.tags.album_artist,
                'genre': self.tags.genre,
                'date': year,
                'discnumber': disc_number,
                'tracknumber': track_number,
            }

            # Очищаем существующие теги
            easy_tags.delete()
            
            # Записываем новые теги через EasyID3
            for key, value in tag_mapping.items():
                if value:
                    try:
                        easy_tags[key] = [value]
                    except Exception as e:
                        log.error(f"Failed to write tag {key}: {e}")

            # Сохраняем основные теги
            easy_tags.save()

            # Перезагружаем ID3 теги после сохранения EasyID3
            id3 = ID3(self.filepath)

            # Удаляем существующие комментарии
            for key in list(id3.keys()):
                if key.startswith('COMM:'):
                    del id3[key]

            # Добавляем новые комментарии
            if self.tags.comment:
                id3.add(COMM(encoding=3, lang='eng', desc='', text=self.tags.comment))
            
            if self.tags.rating:
                id3.add(COMM(encoding=3, lang='eng', desc='Rating', text=f"Rating: {self.tags.rating}"))
            
            if self.tags.lastfm_tags:
                id3.add(COMM(encoding=3, lang='eng', desc='LastFM tags', 
                            text=f"LastFM tags: {self.tags.lastfm_tags}"))

            # Add or update album cover
            if self.tags.album_cover:
                # Remove existing covers
                for key in list(id3.keys()):
                    if key.startswith('APIC:'):
                        del id3[key]
                
                # Add new cover
                id3.add(APIC(
                    encoding=3,  # UTF-8
                    mime=self.tags.album_cover_mime,
                    type=3,  # Cover (front)
                    desc='Cover',
                    data=self.tags.album_cover
                ))
            
            # Add lyrics if available
            if self.tags.lyrics:
                id3.add(USLT(
                    encoding=3,  # UTF-8
                    lang='eng',  # Language code
                    desc='',     # Description
                    text=self.tags.lyrics
                ))

            # Save all changes
            id3.save(v2_version=3)
            
            log.debug(f"Tags successfully written to {self.filepath}")
            
            # Проверяем, что теги действительно записались
            verification_tags = EasyID3(self.filepath)
            for key, value in tag_mapping.items():
                if value and (key not in verification_tags or verification_tags[key][0] != value):
                    log.warning(f"Tag verification failed for {key}: expected '{value}', got '{(verification_tags.get(key) or [''])[0]}'")

        except Exception as e:
            log.error(f"Error writing tags to {self.filepath}: {e}")

    def calculate_new_paths_from_tags(self) -> Optional[Path]:
        """Вычисляет новый путь для файла на основе тегов и конфигурации."""
        try:
            base_dir = Path(cfg.collection.directory)
            
            genre_pattern = cfg.paths.patterns.genre

            if self.song_dir and self.song_dir.is_compilation:
                pattern = cfg.paths.patterns.compilation
            else:
                pattern = cfg.paths.patterns.album

            # Добавляем номер диска только если их больше одного
            if not self.tags.total_discs or int(self.tags.total_discs) <= 1:
                pattern = pattern.replace(' (CD%disc_num)', '')
                genre_pattern = genre_pattern.replace(' (CD%disc_num)', '')

            # Словарь для сопоставления переменных паттерна с полями AudioTags
            tag_mapping = {
                'song_title': sanitize_path_component(str(self.tags.title)),
                'song_artist': sanitize_path_component(str(self.tags.artist)),
                'album_title': sanitize_path_component(str(self.tags.album)),
                'album_artist': sanitize_path_component(str(self.tags.album_artist)),
                'track_num': str(self.tags.track_number).zfill(2) if self.tags.track_number else 'XX',
                'num_of_tracks': str(self.tags.total_tracks) if self.tags.total_tracks else 'XX',
                'disc_num': str(self.tags.disc_number) if self.tags.disc_number else '1',
                'genre': sanitize_path_component(str(self.tags.genre)),
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
        from rich import print
        from rich.panel import Panel
        from rich.console import Console
        from rich.text import Text

        console = Console(width=100)
        panel_width = 98  # Slightly less than console width to avoid wrapping

        # Создаем панель для изменений тегов
        if self.old_tags != self.tags:
            tag_changes = []
            for field in ['title', 'artist', 'album', 'album_artist', 
                         'genre', 'year', 'track_number', 'total_tracks', 
                         'disc_number', 'total_discs', 'lastfm_tags', 'comment']:
                old_value = getattr(self.old_tags, field, '')
                new_value = getattr(self.tags, field, '')
                if old_value != new_value:
                    tag_changes.append(
                        f"[cyan]{field}[/cyan]\n"
                        f"  [yellow]Old:[/yellow] {old_value or '[red]<empty>[/red]'}\n"
                        f"  [green]New:[/green] {new_value or '[red]<empty>[/red]'}"
                    )
            
            if tag_changes:
                tag_panel = Panel(
                    "\n".join(tag_changes),
                    title="[bold magenta]Tag Changes[/]",
                    width=panel_width,
                    border_style="magenta"
                )
                console.print(tag_panel)

        # Выводим изменение пути файла
        if self.filepath != self.new_filepath:
            path_content = (
                f"[yellow]Current:[/yellow] {self.filepath}\n"
                f"[green]New:[/green] {self.new_filepath}"
            )
            path_panel = Panel(
                path_content,
                title="[bold magenta]File Path Change[/]",
                width=panel_width,
                border_style="magenta"
            )
            console.print(path_panel)

        # Выводим информацию о символических ссылках для жанров
        if self.genre_paths:
            genre_content = "\n".join(f"[green]{path}[/green]" for path in self.genre_paths)
            genre_panel = Panel(
                genre_content,
                title="[bold magenta]Genre Symlinks[/]",
                width=panel_width,
                border_style="magenta"
            )
            console.print(genre_panel)

        # Выводим информацию об обложке альбома
        if self.tags.album_cover:
            cover_size = len(self.tags.album_cover) / 1024  # Convert to KB
            cover_content = (
                f"[green]Cover image present[/green]\n"
                f"Size: [cyan]{cover_size:.1f}[/cyan] KB\n"
                f"Type: [cyan]{self.tags.album_cover_mime}[/cyan]"
            )
            cover_panel = Panel(
                cover_content,
                title="[bold magenta]Album Cover[/]",
                width=panel_width,
                border_style="magenta"
            )
            console.print(cover_panel)

        # Выводим информацию о текстах песен
        if self.tags.lyrics:
            lyrics_preview = self.tags.lyrics[:200] + "..." if len(self.tags.lyrics) > 200 else self.tags.lyrics
            lyrics_content = (
                f"[green]Lyrics present[/green]\n"
                f"Length: [cyan]{len(self.tags.lyrics)}[/cyan] characters\n"
                f"Preview:\n[yellow]{lyrics_preview}[/yellow]"
            )
            lyrics_panel = Panel(
                lyrics_content,
                title="[bold magenta]Lyrics[/]",
                width=panel_width,
                border_style="magenta"
            )
            console.print(lyrics_panel)

        # Выводим разделитель
        console.print("[dim]" + "─" * panel_width + "[/dim]")

    def __str__(self):
        return (
            f"{self.filepath}\n\n"
            f"Artist: {self.tags.artist}\n"
            f"Title: {self.tags.title}\n"
            f"Album artist: {self.tags.album_artist}\n"
            f"Album title: {self.tags.album}\n"
            f"Compilation: {self.tags.compilation}\n"
            f"Year: {self.tags.year}\n"
            f"Track: {self.tags.track_number}/{self.tags.total_tracks}"
            f"Genre: {self.tags.genre}\n"
            f"Tags: {self.tags.lastfm_tags}\n"
            f"Rating: {self.tags.rating}\n"
        )

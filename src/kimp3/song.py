# -*- coding: utf-8 -*-
# pyright: basic
# pyright: reportAttributeAccessIssue=false

import logging
from pathlib import Path
from typing import List

import kimp3.tags
from kimp3.backends import TagWritePolicy, get_backend
from kimp3.config import APP_NAME, cfg
from kimp3.encoding import repair_audio_tags_text_encoding
from kimp3.interface.utils import yes_or_no
from kimp3.models import AbstractSongDir, AudioTags, FileOperation, UsualFile
from kimp3.planning import OperationPlan, build_operation_plan
from kimp3.title_case import normalize_audio_tag_titles

log = logging.getLogger(f"{APP_NAME}.{__name__}")


class AudioFile(UsualFile):
    """Class for working with MP3 files, including tags and file operations."""
    
    def __init__(self, filepath: str | Path, song_dir: AbstractSongDir):
        super().__init__(filepath, song_dir)
        
        self.genre_paths: List[Path] = []
        self.tags = self._read_tags()
        self.original_tags = self.tags.model_copy(deep=True)
        self.tags = repair_audio_tags_text_encoding(self.tags)
        self.tags = normalize_audio_tag_titles(self.tags, cfg.tags)
        self.old_tags = AudioTags()
        self.skip_tag_write = False
        self.tag_write_success = False
        self.operation_plan: OperationPlan | None = None

    def _read_tags(self) -> AudioTags:
        """Reads tags from file using mutagen."""
        try:
            tags = get_backend(self.filepath).read(self.filepath)
            if tags.lyrics:
                log.debug(f"`tags`Found lyrics: {tags.lyrics.text[:100]}...")
            else:
                log.debug("`tags`No lyrics found in file")
            return tags

        except Exception as e:
            log.error(f"`files,tags`Error reading tags from {self.filepath}: {e}")
            log.exception("`files,tags`Full traceback:")
            return AudioTags()
    
    def process_missing_tags_from_local_data(self) -> None:
        """Process tags from local data if some are missing."""
        if not self.tags.album_artist:
            self.tags.album_artist = self.tags.artist
        if not self.tags.total_tracks and self.song_dir.track_count:
            self.tags.total_tracks = self.song_dir.track_count

    def fetch_tags(self) -> dict[str, tuple[str, str]]:
        """Checks and corrects tags via Last.FM.
        
        Returns:
            Dictionary of changes in format {field: (old_value, new_value)}
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
            # Update tags via Last.FM
            if cfg.tags.fetch_tags:
                self.tags = kimp3.tags.TaggedTrack(self.tags, self.song_dir).get_audiotags()
            
            # Handle 'The' article in artist name
            for field in ['artist', 'album_artist']:
                value = getattr(self.tags, field, '')
                if value.lower().startswith('the '):
                    if cfg.tags.the_the == 'remove':
                        setattr(self.tags, field, value[4:])
                    elif cfg.tags.the_the == 'move':
                        setattr(self.tags, field, value[4:] + ', the')

            self.tags = normalize_audio_tag_titles(self.tags, cfg.tags)

            # Collect changes
            for field in AudioTags.__annotations__:
                old_value = getattr(self.old_tags, field)
                new_value = getattr(self.tags, field)
                
                if old_value != new_value:
                    changes[field] = (old_value or '<empty>', new_value or '<empty>')

        except Exception as e:
            log.error(f"`network,tags`Error fetching tags for {self.filepath}: {e}")
        
        return changes

    def write_tags(self) -> bool:
        """Writes tags to file."""
        try:
            get_backend(self.filepath).write(self.filepath, self.tags, TagWritePolicy())
            log.debug(f"`files,tags`Tags successfully written to {self.filepath}")
            if not cfg.scan.verify_after_write:
                return True
            return self.verify_tags()

        except Exception as e:
            log.error(f"`files,tags`Error writing tags to {self.filepath}: {e}")
            return False

    def tags_changed(self) -> bool:
        """Return True when planned tags differ from what was read initially."""
        if self.operation_plan:
            return self.operation_plan.tags.requires_write
        return not self.tags.managed_equals(self.original_tags)

    def verify_tags(self) -> bool:
        """Read the file again and verify managed tags match the plan."""
        errors = get_backend(self.filepath).verify(self.filepath, self.tags, TagWritePolicy())
        if not errors:
            return True
        for error in errors:
            log.error(f"`files,tags`{error}")
        return False

    def calculate_new_paths_from_tags(self) -> None:
        """Calculates new path for file based on tags and configuration."""
        self.genre_paths = []
        try:
            plan = build_operation_plan(self.filepath, self.original_tags, self.tags, self.song_dir, cfg)
            self.operation_plan = plan
            self.operation_processed = FileOperation.NONE
            self.planned_operation = plan.operation
            self.new_filepath = plan.path.target_path
            self.genre_paths = plan.path.genre_links
            self.skip_tag_write = not plan.requires_tag_write

        except Exception as e:
            log.error(f"`files`Error calculating new path for {self.filepath}: {e}")

    def print_changes(self, 
                      show_tags: bool = False,
                      show_path: bool = False,
                      show_genre_links: bool = False,
                      show_lyrics: bool = False,
                      show_cover: bool = False) -> None:
        """Prints tag and path changes."""
        from rich import print
        from rich.console import Console
        from rich.panel import Panel
        from rich.text import Text

        console = Console(width=100)
        panel_width = 98  # Slightly less than console width to avoid wrapping

        # Create panel for tag changes
        if show_tags and self.old_tags != self.tags:
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

        # Print path change
        if show_path and self.filepath != self.new_filepath:
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

        # Print genre links
        if show_genre_links and self.genre_paths:
            genre_content = "\n".join(f"[green]{path}[/green]" for path in self.genre_paths)
            genre_panel = Panel(
                genre_content,
                title="[bold magenta]Genre Symlinks[/]",
                width=panel_width,
                border_style="magenta"
            )
            console.print(genre_panel)

        # Print album cover
        if show_cover and self.tags.album_cover:
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

        # Print lyrics
        if show_lyrics and self.tags.lyrics:
            lyrics_text = self.tags.lyrics.text
            lyrics_preview = lyrics_text[:200] + "..." if len(lyrics_text) > 200 else lyrics_text
            lyrics_content = (
                f"[green]Lyrics present[/green]\n"
                f"Length: [cyan]{len(lyrics_text)}[/cyan] characters\n"
                f"Preview:\n[yellow]{lyrics_preview}[/yellow]"
            )
            lyrics_panel = Panel(
                lyrics_content,
                title="[bold magenta]Lyrics[/]",
                width=panel_width,
                border_style="magenta"
            )
            console.print(lyrics_panel)


    def __str__(self):
        return (
            f"{self.filepath}\n\n"
            f"Artist: {self.tags.artist}\n"
            f"Title: {self.tags.title}\n"
            f"Album artist: {self.tags.album_artist}\n"
            f"Album title: {self.tags.album}\n"
            f"Compilation: {self.tags.compilation}\n"
            f"Year: {self.tags.year}\n"
            f"Track: {self.tags.track_number}/{self.tags.total_tracks}\n"
            f"Genre: {self.tags.genre}\n"
            f"Tags: {self.tags.lastfm_tags}\n"
            f"Rating: {self.tags.rating}\n"
        )

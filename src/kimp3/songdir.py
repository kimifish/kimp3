#  -*- coding: utf-8 -*-
# pyright: basic
# pyright: reportAttributeAccessIssue=false

import logging
from kimp3.interface.utils import yes_or_no
from kimp3.song import AudioFile, UsualFile
from pathlib import Path
from rich.pretty import pretty_repr
from typing import List, Set, Optional, Dict
from kimp3.config import cfg, APP_NAME
from kimp3.checks import test_is_album, test_is_compilation
from kimp3.models import AbstractSongDir, FileOperation
from kimp3.planning import PathPlan, score_candidate, validate_audio_plans, validate_operation_plans

log = logging.getLogger(f"{APP_NAME}.{__name__}")


class SongDir(AbstractSongDir):
    """Concrete implementation of song directory management.
    
    Implements all abstract methods defined in AbstractSongDir for scanning,
    analyzing and processing audio files in a directory.
    """
    
    def __init__(self, scan_path: str | Path, parent=None):
        """Initialize SongDir with path and scan for audio files.
        
        Args:
            scan_path: Directory path to scan
            parent: Optional parent scanner reference
        """
        super().__init__(scan_path)
        self.parent = parent

        self._scan_directory()
        self._analyze_directory()
        if self.is_album:
            self._count_tracks()

        if cfg.logging.level == 'DEBUG':
            log.debug(pretty_repr(self.stats))

    def _scan_directory(self) -> None:
        """Scan directory for audio files and common album files."""
        try:
            for entry in self.path.iterdir():
                if not entry.is_file():
                    continue
                    
                if entry.suffix.lower() in cfg.scan.valid_extensions:
                    log.debug(f"+ {str(entry).replace(str(self.path), '…')}")
                    audio_file = AudioFile(filepath=entry, song_dir=self)
                    if audio_file:
                        self.audio_files.append(audio_file)
                elif entry.name.lower() in [f.lower() for f in cfg.scan.common_files]:
                    log.debug(f"+ {str(entry).replace(str(self.path), '…')}")
                    self.common_files.append(UsualFile(filepath=entry, song_dir=self))

        except OSError as e:
            log.error(f"Error scanning directory {self.path}: {e}")

    def _analyze_directory(self) -> None:
        """Analyze directory contents to determine if it's an album/compilation."""
        if not self.audio_files:
            return

        # Проверяем, является ли каталог альбомом
        is_album, album_title = test_is_album(self)
        self.is_album = is_album
        self.album_title = album_title

        if self.is_album and cfg.collection.compilation_test:
            # Проверяем, является ли альбом сборником
            is_compilation, album_artist = test_is_compilation(self)
            self.is_compilation = is_compilation
            self.album_artist = album_artist

    def _count_tracks(self) -> None:
        """Count total tracks in album based on track numbers and file count."""
        max_track_num = 0
        for audio_file in self.audio_files:
            if audio_file.tags.track_number:
                max_track_num = max(max_track_num, audio_file.tags.track_number)
                
        self.track_count = max(max_track_num, len(self.audio_files))
        log.debug(f"Track count set to {self.track_count}")

    def _process_audio_files(self, operation: FileOperation) -> None:
        """Process audio files according to specified operation.

        Args:
            operation: FileOperation enum value (COPY/MOVE/NONE)
        """
        if not self.audio_files:
            return

        for audio_file in self.audio_files:
            audio_file.calculate_new_paths_from_tags()
            _ = getattr(audio_file, "planned_operation", operation)
        self._resolve_duplicate_track_numbers()

    def _resolve_duplicate_track_numbers(self) -> None:
        """Warn and clear track number for weaker duplicate track-number candidates."""
        groups = {}
        for audio_file in self.audio_files:
            plan = audio_file.operation_plan
            if not plan or not audio_file.tags.track_number:
                continue
            key = (plan.path.target_path.parent, audio_file.tags.disc_number, audio_file.tags.track_number)
            groups.setdefault(key, []).append(audio_file)
        for (_album_dir, _disc, track_number), files in groups.items():
            if len(files) <= 1:
                continue
            winner = max(files, key=lambda item: score_candidate(item.filepath, item.tags).score)
            for audio_file in files:
                if audio_file is winner:
                    continue
                warning = (
                    f"Duplicate track number {track_number}; clearing track number for weaker candidate "
                    f"{audio_file.filepath}"
                )
                log.warning(warning)
                audio_file.tags.track_number = None
                audio_file.calculate_new_paths_from_tags()
                if audio_file.operation_plan:
                    audio_file.operation_plan.warnings.append(warning)

    def _process_common_files(self, operation: FileOperation) -> None:
        """Process common album files like artwork.
        
        Args:
            operation: FileOperation enum value (COPY/MOVE)
        """
        if not self.common_files or not self.audio_files:
            return
        resolved_operation = getattr(self.audio_files[0], "planned_operation", operation)
            
        # Get target directory from first audio file that has new_filepath
        target_dir = None
        for audio_file in self.audio_files:
            if hasattr(audio_file, 'new_filepath') and audio_file.new_filepath:
                target_dir = audio_file.new_filepath.parent
                break
                
        if not target_dir:
            log.warning("Could not determine target directory for common files")
            return
        
        for common_file in self.common_files:
            common_file.new_filepath = target_dir / common_file.name
            
            _ = resolved_operation

    def process_files(self, operation: FileOperation) -> None:
        """Process all files in directory.
        
        Args:
            operation: FileOperation enum value (COPY/MOVE/NONE)
        """
        # First process audio files to calculate new paths
        self._process_audio_files(operation)
        # Then process common files using the calculated paths
        self._process_common_files(operation)

    def validate_plans(self) -> list[str]:
        """Validate planned audio operations before filesystem writes."""
        operation_plans = [audio_file.operation_plan for audio_file in self.audio_files if audio_file.operation_plan]
        if operation_plans:
            return validate_operation_plans(operation_plans)
        plans = [
            PathPlan(
                source_path=audio_file.filepath,
                target_path=audio_file.new_filepath,
                genre_links=audio_file.genre_paths,
                operation=getattr(audio_file, "planned_operation", cfg.scan.operation),
            )
            for audio_file in self.audio_files
            if audio_file.new_filepath
        ]
        return validate_audio_plans(plans)

    def fetch_tags(self):
        """Check and correct tags for all songs in directory."""
        log.info("Fetching tags...")
        changes = {}
        for audio_file in self.audio_files:
            changes[str(audio_file.filepath).replace(str(self.path.parent), '')] = audio_file.fetch_tags()
        return changes

    def gather_tag_values(self, tag_name: str) -> Set[str]:
        """Gather unique values of specified tag from all audio files.
        
        Args:
            tag_name: Name of the tag to gather
            
        Returns:
            Set of unique tag values
        """
        values = set()
        for audio_file in self.audio_files:
            value = getattr(audio_file.tags, tag_name)
            if value:
                values.add(value)
        return values

    def write_tags(self) -> tuple:
        """Write tags to all audio files in directory.
        
        Returns:
            tuple: (number of successful writes, number of failed writes)
        """
        successes = 0
        failures = 0
        skips = 0
        interactive = cfg.interactive
        answer = 'y'
        
        for audio_file in self.audio_files:
            if getattr(audio_file, "skip_tag_write", False):
                audio_file.tag_write_success = True
                skips += 1
                continue
            if getattr(audio_file, "planned_operation", None) == FileOperation.NONE:
                audio_file.tag_write_success = True
                skips += 1
                continue
            if cfg.dry_run:
                audio_file.tag_write_success = True
                log.info(f"Dry run - would write tags to {audio_file.filepath}")
                skips += 1
                continue
            if interactive:
                audio_file.print_changes(show_tags=True, show_cover=True, show_lyrics=True)
                answer = yes_or_no("Write tags?", "yYnN")

            if answer in 'YN':
                interactive = False

            if answer.lower() == 'n':
                audio_file.tag_write_success = False
                skips += 1
                continue

            if audio_file.write_tags():
                audio_file.tag_write_success = True
                successes += 1
            else:
                audio_file.tag_write_success = False
                failures += 1
        
        if successes > 0:
            log.info(f"[green]Successfully wrote tags to {successes} files[/green]")
        if failures > 0:
            log.error(f"[red]Failed to write tags to {failures} files[/red]")
        if skips > 0:
            log.info(f"[yellow]Skipped writing tags to {skips} files[/yellow]")
            
        return (successes, failures, skips)
    
    def process_missing_tags_from_local_data(self) -> None:
        """Process missing tags from local data for all audio files."""
        for audio_file in self.audio_files:
            audio_file.process_missing_tags_from_local_data()

    @property
    def stats(self) -> Dict:
        """Get directory statistics.
        
        Returns:
            Dictionary with directory statistics
        """
        return {
            'path': str(self.path),
            'audio_files': len(self.audio_files),
            'is_album': self.is_album,
            'is_compilation': self.is_compilation,
            'album_title': self.album_title,
            'album_artist': self.album_artist,
            'track_count': self.track_count,
            'common_files': len(self.common_files)
        }

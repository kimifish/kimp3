from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from kimp3.backends import TagWritePolicy, get_backend
from kimp3.config import APP_NAME, cfg
from kimp3.interface.utils import yes_or_no
from kimp3.models import FileOperation, UsualFile
from kimp3.planning import build_tag_change_plan
from kimp3.reporting import ExecutionReporter, PlanReporter, execution_result_to_report_dict
from kimp3.song import AudioFile


log = logging.getLogger(f"{APP_NAME}.{__name__}")


@dataclass
class ExecutionResult:
    """Summary of plan execution."""

    successes: int = 0
    failures: int = 0
    skips: int = 0
    errors: list[str] = field(default_factory=list)

    def as_tuple(self) -> tuple[int, int, int]:
        return self.successes, self.failures, self.skips

    def to_report_dict(self) -> dict[str, object]:
        return execution_result_to_report_dict(self)


class OperationExecutor:
    """Execute built OperationPlans without the legacy global operation lists."""

    def __init__(self, dry_run: bool | None = None, interactive: bool | None = None) -> None:
        self.dry_run = cfg.dry_run if dry_run is None else dry_run
        self.interactive = cfg.interactive if interactive is None else interactive
        self._suppress_individual_preview = False

    def execute_song_dir(self, song_dir: object) -> ExecutionResult:
        """Execute all audio plans and common-file operations for one song directory."""
        result = ExecutionResult()
        completed_audio = []
        plans = [audio_file.operation_plan for audio_file in song_dir.audio_files if audio_file.operation_plan]
        if self.dry_run and plans:
            PlanReporter().print_full_preview(plans, title=f"Dry Run: {song_dir.path}")
            self._suppress_individual_preview = True
        for audio_file in song_dir.audio_files:
            file_result = self.execute_audio_file(audio_file)
            result.successes += file_result.successes
            result.failures += file_result.failures
            result.skips += file_result.skips
            result.errors.extend(file_result.errors)
            if file_result.successes > 0 or file_result.skips > 0:
                completed_audio.append(audio_file)

        if completed_audio:
            self._execute_common_files(song_dir.common_files, completed_audio[0], result)
        if self.dry_run:
            self._suppress_individual_preview = False
        return result

    def cleanup_collection(self, roots: list[Path] | None = None) -> None:
        """Run collection maintenance tasks handled by the executor."""
        self._clean_broken_genre_symlinks()
        if cfg.scan.delete_empty_dirs:
            for root in roots or [Path(cfg.collection.directory)]:
                root_path = Path(root)
                self._remove_junk_files(root_path, stop_at=root_path)
                self._cleanup_empty_dirs(root_path, stop_at=root_path.parent)

    def execute_audio_file(self, audio_file: AudioFile) -> ExecutionResult:
        """Execute one planned audio-file operation and run full verification."""
        result = ExecutionResult()
        plan = audio_file.operation_plan
        source_parent = plan.path.source_path.parent if plan else None
        if plan is None:
            result.skips += 1
            return result
        if plan.errors:
            for error in plan.errors:
                log.error(error)
            result.failures += 1
            result.errors.extend(plan.errors)
            return result
        if plan.skip_execution:
            log.warning(plan.skip_reason)
            result.skips += 1
            return result
        if plan.operation == FileOperation.NONE:
            if not self._suppress_individual_preview:
                self.preview_plan(plan)
            result.skips += 1
            return result

        if self.dry_run:
            if not self._suppress_individual_preview:
                self.preview_plan(plan)
            result.skips += 1
            return result

        if self.interactive:
            audio_file.print_changes(show_tags=True, show_path=True, show_genre_links=True, show_cover=True, show_lyrics=True)
            if yes_or_no("Proceed?", "yYnN").lower() == "n":
                result.skips += 1
                return result

        try:
            if plan.operation == FileOperation.COPY:
                self._execute_copy(audio_file)
            elif plan.operation == FileOperation.MOVE:
                self._execute_move(audio_file)
            self._sync_genre_symlinks(plan.path.target_path, plan.path.genre_links)
            self._cleanup_stale_genre_symlinks(plan.path.target_path, plan.path.genre_links)
            verify_errors = self.verify_audio_file(audio_file)
            if verify_errors:
                result.failures += 1
                result.errors.extend(verify_errors)
                for error in verify_errors:
                    log.error(error)
                return result
            if plan.operation == FileOperation.MOVE and source_parent:
                self._remove_junk_files(source_parent, stop_at=source_parent)
                self._cleanup_empty_dirs(source_parent, stop_at=source_parent.parent)
            self._clean_broken_genre_symlinks()
            result.successes += 1
            return result
        except Exception as error:
            message = f"Failed to execute plan for {audio_file.filepath}: {error}"
            log.error(message)
            result.failures += 1
            result.errors.append(message)
            return result

    def verify_audio_file(self, audio_file: AudioFile) -> list[str]:
        """Verify path, managed tags and planned genre symlinks."""
        plan = audio_file.operation_plan
        if plan is None or plan.operation == FileOperation.NONE:
            return []
        errors: list[str] = []
        target_path = plan.path.target_path
        if audio_file.filepath != target_path:
            errors.append(f"Path verification failed: expected {target_path}, got {audio_file.filepath}")
        if not target_path.exists():
            errors.append(f"Path verification failed: target does not exist: {target_path}")
        else:
            errors.extend(get_backend(target_path).verify(target_path, plan.tags.target_tags, TagWritePolicy()))
        for link_path in plan.path.genre_links:
            if not link_path.is_symlink():
                errors.append(f"Symlink verification failed: missing symlink {link_path}")
                continue
            actual_target = Path(os.readlink(link_path))
            if not actual_target.is_absolute():
                actual_target = (link_path.parent / actual_target).resolve()
            if actual_target != target_path.resolve():
                errors.append(f"Symlink verification failed: {link_path} points to {actual_target}, expected {target_path}")
        return errors

    def preview_plan(self, plan: object) -> None:
        """Log a read-only operation preview."""
        PlanReporter().print_plan_detail(plan)

    def _execute_copy(self, audio_file: AudioFile) -> None:
        plan = audio_file.operation_plan
        target_path = plan.path.target_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target_path.with_name(f".{target_path.stem}.tmp-kimp3{target_path.suffix}")
        self._merge_existing_target_metadata(plan)
        if target_path.exists() and plan.replace_existing:
            target_path.unlink()
        if target_path.exists():
            raise FileExistsError(f"Target already exists: {target_path}")
        shutil.copyfile(plan.path.source_path, tmp_path)
        original_path = audio_file.filepath
        audio_file.filepath = tmp_path
        try:
            if plan.requires_tag_write and not audio_file.write_tags():
                raise RuntimeError("Tag write/verify failed")
            os.replace(tmp_path, target_path)
            audio_file.filepath = target_path
            audio_file.operation_processed = FileOperation.COPY
            audio_file.tag_write_success = True
        except Exception:
            audio_file.filepath = original_path
            if tmp_path.exists():
                tmp_path.unlink()
            audio_file.tag_write_success = False
            raise

    def _execute_move(self, audio_file: AudioFile) -> None:
        plan = audio_file.operation_plan
        target_path = plan.path.target_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        self._merge_existing_target_metadata(plan)
        if plan.requires_tag_write and not audio_file.write_tags():
            audio_file.tag_write_success = False
            raise RuntimeError("Tag write/verify failed")
        audio_file.tag_write_success = True
        if audio_file.filepath == target_path:
            audio_file.operation_processed = FileOperation.MOVE
            return
        if target_path.exists() and plan.replace_existing:
            target_path.unlink()
        if target_path.exists():
            raise FileExistsError(f"Target already exists: {target_path}")
        moved_path = shutil.move(audio_file.filepath, target_path)
        audio_file.filepath = Path(moved_path)
        audio_file.operation_processed = FileOperation.MOVE

    def _merge_existing_target_metadata(self, plan: object) -> None:
        """Keep selected library metadata when replacing an existing target."""
        if not getattr(plan, "replace_existing", False) or not plan.path.target_path.exists():
            return
        try:
            existing_tags = get_backend(plan.path.target_path).read(plan.path.target_path)
        except Exception as error:
            log.warning(f"Could not read existing target artwork for merge: {error}")
            return
        existing_cover = existing_tags.album_cover
        planned_cover = plan.tags.target_tags.album_cover
        changed = False
        if existing_cover and (not planned_cover or len(existing_cover) > len(planned_cover)):
            plan.tags.target_tags.artwork = existing_tags.artwork
            changed = True
            log.info(
                "Keeping larger existing artwork "
                f"({len(existing_cover)} bytes > {len(planned_cover) if planned_cover else 0} bytes)"
            )
        if existing_tags.lyrics:
            plan.tags.target_tags.lyrics = existing_tags.lyrics
            changed = True
            log.info("Keeping existing library lyrics")
        if existing_tags.rating is not None:
            plan.tags.target_tags.rating = existing_tags.rating
            changed = True
            log.info("Keeping existing library rating")
        if changed:
            plan.tags = build_tag_change_plan(plan.tags.source_tags, plan.tags.target_tags)

    def _sync_genre_symlinks(self, target_path: Path, genre_links: list[Path]) -> None:
        for link_path in genre_links:
            link_path.parent.mkdir(parents=True, exist_ok=True)
            if link_path.exists() or link_path.is_symlink():
                if link_path.is_symlink():
                    current_target = Path(os.readlink(link_path))
                    if not current_target.is_absolute():
                        current_target = (link_path.parent / current_target).resolve()
                    if current_target == target_path.resolve():
                        continue
                    link_path.unlink()
                else:
                    log.warning(f"Replacing non-symlink path in genre directory: {link_path}")
                    if link_path.is_dir():
                        shutil.rmtree(link_path)
                    else:
                        link_path.unlink()
            relative_target = os.path.relpath(target_path, link_path.parent)
            link_path.symlink_to(relative_target)

    def _cleanup_stale_genre_symlinks(self, target_path: Path, planned_links: list[Path]) -> None:
        genre_dir = self._genre_base_dir()
        if genre_dir is None or not genre_dir.exists():
            return
        planned = {link.absolute() for link in planned_links}
        target = target_path.resolve()
        for link_path in genre_dir.rglob("*"):
            if not link_path.is_symlink():
                continue
            raw_target = Path(os.readlink(link_path))
            actual_target = raw_target if raw_target.is_absolute() else (link_path.parent / raw_target).resolve()
            if actual_target == target and link_path.absolute() not in planned:
                log.info(f"Removing stale genre symlink: {link_path}")
                link_path.unlink()

    def _genre_base_dir(self) -> Path | None:
        genre_base = cfg.paths.patterns.genre.split("/")[0]
        if not genre_base or "%" in genre_base:
            return None
        return Path(cfg.collection.directory) / genre_base

    def _clean_broken_genre_symlinks(self) -> None:
        if not cfg.collection.clean_symlinks:
            return
        genre_dir = self._genre_base_dir()
        if genre_dir is None or not genre_dir.exists():
            return
        for link_path in genre_dir.rglob("*"):
            if not link_path.is_symlink():
                continue
            raw_target = Path(os.readlink(link_path))
            actual_target = raw_target if raw_target.is_absolute() else (link_path.parent / raw_target).resolve()
            if not actual_target.exists():
                log.info(f"Removing broken genre symlink: {link_path}")
                if not self.dry_run:
                    link_path.unlink()
        self._remove_junk_files(genre_dir, stop_at=genre_dir)
        self._cleanup_empty_dirs(genre_dir, stop_at=genre_dir)

    def _remove_junk_files(self, root_dir: Path, stop_at: Path | None = None) -> None:
        junk_names = set(cfg.scan.junk_files)
        if not junk_names:
            return
        root = root_dir.resolve(strict=False)
        stop = (stop_at or Path(cfg.collection.directory)).resolve(strict=False)
        if root != stop and stop not in root.parents:
            return
        if not root.exists():
            return
        for path in root.rglob("*"):
            if path.is_file() and not path.is_symlink() and path.name in junk_names:
                log.info(f"Removing junk file: {path}")
                if not self.dry_run:
                    path.unlink()

    def _cleanup_empty_dirs(self, start_dir: Path, stop_at: Path | None = None) -> None:
        if not cfg.scan.delete_empty_dirs:
            return
        current = start_dir.resolve(strict=False)
        stop = (stop_at or Path(cfg.collection.directory)).resolve(strict=False)
        if current != stop and stop not in current.parents:
            return
        while current != stop and current != current.parent:
            try:
                if not current.exists() or any(current.iterdir()):
                    break
                if self.dry_run:
                    log.info(f"Dry run - would delete empty {current}")
                    break
                current.rmdir()
                log.info(f"Deleting empty {current}")
            except OSError:
                break
            current = current.parent

    def _execute_common_files(self, common_files: list[UsualFile], first_audio: AudioFile, result: ExecutionResult) -> None:
        if not common_files or first_audio.operation_plan is None:
            return
        operation = first_audio.operation_plan.operation
        if operation not in {FileOperation.COPY, FileOperation.MOVE}:
            return
        target_dir = first_audio.operation_plan.path.target_path.parent
        for common_file in common_files:
            target_path = target_dir / common_file.name
            common_file.new_filepath = target_path
            if self.dry_run:
                continue
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                if common_file.filepath == target_path:
                    continue
                if target_path.exists():
                    raise FileExistsError(f"Target already exists: {target_path}")
                if operation == FileOperation.COPY:
                    shutil.copyfile(common_file.filepath, target_path)
                    common_file.operation_processed = FileOperation.COPY
                else:
                    moved_path = shutil.move(common_file.filepath, target_path)
                    common_file.filepath = Path(moved_path)
                    common_file.operation_processed = FileOperation.MOVE
            except Exception as error:
                message = f"Failed to process common file {common_file.filepath}: {error}"
                log.error(message)
                result.errors.append(message)

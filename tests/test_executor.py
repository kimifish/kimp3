import os
from pathlib import Path

import pytest

from kimp3.executor import ExecutionResult, OperationExecutor
from kimp3.models import AudioTags, FileOperation, UsualFile
from kimp3.planning import OperationPlan, PathPlan, build_tag_change_plan


class FakeBackend:
    def verify(self, path: Path, expected: AudioTags, policy):
        return [] if path.exists() else [f"missing {path}"]


class DummyAudioFile:
    def __init__(
        self,
        source: Path,
        target: Path,
        link: Path,
        requires_tag_write: bool = True,
        operation: FileOperation = FileOperation.COPY,
    ):
        source_tags = AudioTags(
            title="Old" if requires_tag_write else "Song", artist="Artist"
        )
        target_tags = AudioTags(title="Song", artist="Artist")
        self.filepath = source
        self.new_filepath = target
        self.operation_processed = FileOperation.NONE
        self.tag_write_success = False
        self.write_calls = 0
        self.operation_plan = OperationPlan(
            path=PathPlan(
                source_path=source,
                target_path=target,
                genre_links=[link],
                operation=operation,
            ),
            tags=build_tag_change_plan(source_tags, target_tags),
        )

    def write_tags(self):
        self.write_calls += 1
        return True

    def print_changes(self, **kwargs):
        return None


class DummySongDir:
    def __init__(self, audio_files):
        self.audio_files = audio_files
        self.common_files = []


@pytest.fixture(autouse=True)
def configure_genre_root(monkeypatch, tmp_path):
    monkeypatch.setattr("kimp3.executor.cfg.collection.directory", str(tmp_path / "library"))
    monkeypatch.setattr(
        "kimp3.executor.cfg.paths.patterns.genre", "_Genres/%genre/%song_title.mp3"
    )


def test_operation_executor_copy_creates_target_symlink_and_verifies(
    monkeypatch, tmp_path
):
    source = tmp_path / "incoming" / "song.mp3"
    target = tmp_path / "library" / "Artist" / "song.mp3"
    link = tmp_path / "library" / "_Genres" / "Rock" / "song.mp3"
    source.parent.mkdir()
    source.write_bytes(b"audio")
    audio_file = DummyAudioFile(source, target, link)
    monkeypatch.setattr("kimp3.executor.get_backend", lambda path: FakeBackend())

    result = OperationExecutor(dry_run=False, interactive=False).execute_audio_file(
        audio_file
    )

    assert result.as_tuple() == (1, 0, 0)
    assert source.read_bytes() == b"audio"
    assert target.read_bytes() == b"audio"
    assert audio_file.filepath == target
    assert audio_file.write_calls == 1
    assert link.is_symlink()
    assert (link.parent / Path(link.readlink())).resolve() == target.resolve()
    assert (
        OperationExecutor(dry_run=False, interactive=False).verify_audio_file(
            audio_file
        )
        == []
    )


def test_operation_executor_dry_run_creates_nothing(monkeypatch, tmp_path):
    source = tmp_path / "incoming" / "song.mp3"
    target = tmp_path / "library" / "Artist" / "song.mp3"
    link = tmp_path / "library" / "_Genres" / "Rock" / "song.mp3"
    source.parent.mkdir()
    source.write_bytes(b"audio")
    audio_file = DummyAudioFile(source, target, link)
    monkeypatch.setattr("kimp3.executor.get_backend", lambda path: FakeBackend())

    result = OperationExecutor(dry_run=True, interactive=False).execute_audio_file(
        audio_file
    )

    assert result.as_tuple() == (0, 0, 1)
    assert not target.exists()
    assert not link.exists()
    assert audio_file.filepath == source
    assert audio_file.write_calls == 0


def test_operation_executor_move_same_file_with_relative_source(
    monkeypatch, tmp_path
):
    target = tmp_path / "library" / "Artist" / "song.mp3"
    source = Path("library") / "Artist" / "song.mp3"
    link = tmp_path / "library" / "_Genres" / "Rock" / "song.mp3"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"audio")
    monkeypatch.chdir(tmp_path)
    audio_file = DummyAudioFile(
        source,
        target,
        link,
        requires_tag_write=False,
        operation=FileOperation.MOVE,
    )
    monkeypatch.setattr("kimp3.executor.get_backend", lambda path: FakeBackend())

    result = OperationExecutor(dry_run=False, interactive=False).execute_audio_file(
        audio_file
    )

    assert result.as_tuple() == (1, 0, 0)
    assert target.read_bytes() == b"audio"
    assert audio_file.filepath == target
    assert audio_file.write_calls == 0
    assert link.is_symlink()


def test_operation_executor_copy_same_file_with_relative_source(
    monkeypatch, tmp_path
):
    target = tmp_path / "library" / "Artist" / "song.mp3"
    source = Path("library") / "Artist" / "song.mp3"
    link = tmp_path / "library" / "_Genres" / "Rock" / "song.mp3"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"audio")
    monkeypatch.chdir(tmp_path)
    audio_file = DummyAudioFile(source, target, link, requires_tag_write=False)
    monkeypatch.setattr("kimp3.executor.get_backend", lambda path: FakeBackend())

    result = OperationExecutor(dry_run=False, interactive=False).execute_audio_file(
        audio_file
    )

    assert result.as_tuple() == (1, 0, 0)
    assert target.read_bytes() == b"audio"
    assert audio_file.filepath == target
    assert audio_file.write_calls == 0
    assert link.is_symlink()


def test_operation_executor_replaces_existing_when_decided(monkeypatch, tmp_path):
    source = tmp_path / "incoming" / "song.mp3"
    target = tmp_path / "library" / "Artist" / "song.mp3"
    link = tmp_path / "library" / "_Genres" / "Rock" / "song.mp3"
    source.parent.mkdir()
    target.parent.mkdir(parents=True)
    source.write_bytes(b"better")
    target.write_bytes(b"worse")
    audio_file = DummyAudioFile(source, target, link, requires_tag_write=False)
    audio_file.operation_plan.replace_existing = True
    monkeypatch.setattr("kimp3.executor.get_backend", lambda path: FakeBackend())

    result = OperationExecutor(dry_run=False, interactive=False).execute_audio_file(
        audio_file
    )

    assert result.as_tuple() == (1, 0, 0)
    assert target.read_bytes() == b"better"


def test_operation_executor_skips_conflict_loser(monkeypatch, tmp_path):
    source = tmp_path / "incoming" / "song.mp3"
    target = tmp_path / "library" / "Artist" / "song.mp3"
    link = tmp_path / "library" / "_Genres" / "Rock" / "song.mp3"
    source.parent.mkdir()
    target.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    target.write_bytes(b"target")
    audio_file = DummyAudioFile(source, target, link, requires_tag_write=False)
    audio_file.operation_plan.skip_execution = True
    audio_file.operation_plan.skip_reason = "Conflict: existing target kept"
    monkeypatch.setattr("kimp3.executor.get_backend", lambda path: FakeBackend())

    result = OperationExecutor(dry_run=False, interactive=False).execute_audio_file(
        audio_file
    )

    assert result.as_tuple() == (0, 0, 1)
    assert source.read_bytes() == b"source"
    assert target.read_bytes() == b"target"


def test_operation_executor_skips_plan_with_errors(tmp_path):
    source = tmp_path / "incoming" / "song.mp3"
    target = tmp_path / "library" / "Artist" / "song.mp3"
    link = tmp_path / "library" / "_Genres" / "Rock" / "song.mp3"
    source.parent.mkdir()
    source.write_bytes(b"source")
    audio_file = DummyAudioFile(source, target, link, requires_tag_write=False)
    audio_file.operation_plan.errors.append("hard error")

    result = OperationExecutor(dry_run=False, interactive=False).execute_audio_file(
        audio_file
    )

    assert result.as_tuple() == (0, 1, 0)
    assert not target.exists()


def test_common_image_replaces_existing_when_source_is_larger(tmp_path):
    source = tmp_path / "incoming" / "song.mp3"
    target = tmp_path / "library" / "Artist" / "Album" / "song.mp3"
    cover_source = source.parent / "cover.jpg"
    cover_target = target.parent / "cover.jpg"
    link = tmp_path / "library" / "_Genres" / "Rock" / "song.mp3"
    source.parent.mkdir()
    target.parent.mkdir(parents=True)
    source.write_bytes(b"audio")
    cover_source.write_bytes(b"larger-cover")
    cover_target.write_bytes(b"small")
    audio_file = DummyAudioFile(source, target, link, requires_tag_write=False)
    result = ExecutionResult()

    OperationExecutor(dry_run=False, interactive=False)._execute_common_files(
        [UsualFile(cover_source, song_dir=None)], audio_file, result
    )

    assert result.errors == []
    assert cover_target.read_bytes() == b"larger-cover"


def test_common_image_keeps_existing_when_source_is_not_larger(caplog, tmp_path):
    source = tmp_path / "incoming" / "song.mp3"
    target = tmp_path / "library" / "Artist" / "Album" / "song.mp3"
    cover_source = source.parent / "cover.jpg"
    cover_target = target.parent / "cover.jpg"
    link = tmp_path / "library" / "_Genres" / "Rock" / "song.mp3"
    source.parent.mkdir()
    target.parent.mkdir(parents=True)
    source.write_bytes(b"audio")
    cover_source.write_bytes(b"small")
    cover_target.write_bytes(b"larger-cover")
    audio_file = DummyAudioFile(source, target, link, requires_tag_write=False)
    result = ExecutionResult()

    OperationExecutor(dry_run=False, interactive=False)._execute_common_files(
        [UsualFile(cover_source, song_dir=None)], audio_file, result
    )

    assert result.errors == []
    assert cover_target.read_bytes() == b"larger-cover"
    assert "Keeping existing common image" in caplog.text


def test_operation_executor_refuses_non_symlink_genre_path(monkeypatch, tmp_path):
    source = tmp_path / "incoming" / "song.mp3"
    target = tmp_path / "library" / "Artist" / "song.mp3"
    link = tmp_path / "library" / "_Genres" / "Rock" / "song.mp3"
    source.parent.mkdir()
    link.parent.mkdir(parents=True)
    source.write_bytes(b"audio")
    link.write_text("wrong", encoding="utf-8")
    audio_file = DummyAudioFile(source, target, link, requires_tag_write=False)
    monkeypatch.setattr("kimp3.executor.get_backend", lambda path: FakeBackend())

    result = OperationExecutor(dry_run=False, interactive=False).execute_audio_file(
        audio_file
    )

    assert result.as_tuple() == (0, 1, 0)
    assert link.read_text(encoding="utf-8") == "wrong"


def test_operation_executor_refuses_genre_link_outside_genre_root(
    monkeypatch, tmp_path
):
    source = tmp_path / "incoming" / "song.mp3"
    target = tmp_path / "library" / "Artist" / "song.mp3"
    bad_link = target
    source.parent.mkdir()
    source.write_bytes(b"audio")
    audio_file = DummyAudioFile(source, target, bad_link, requires_tag_write=False)
    monkeypatch.setattr("kimp3.executor.get_backend", lambda path: FakeBackend())

    result = OperationExecutor(dry_run=False, interactive=False).execute_audio_file(
        audio_file
    )

    assert result.as_tuple() == (0, 1, 0)
    assert source.exists()
    assert not target.exists()


def test_operation_executor_removes_stale_genre_symlink(monkeypatch, tmp_path):
    source = tmp_path / "incoming" / "song.mp3"
    target = tmp_path / "library" / "Artist" / "song.mp3"
    planned_link = tmp_path / "library" / "_Genres" / "Rock" / "song.mp3"
    stale_link = tmp_path / "library" / "_Genres" / "Old" / "song.mp3"
    source.parent.mkdir()
    stale_link.parent.mkdir(parents=True)
    source.write_bytes(b"audio")
    target.parent.mkdir(parents=True)
    stale_link.symlink_to(os.path.relpath(target, stale_link.parent))
    audio_file = DummyAudioFile(source, target, planned_link, requires_tag_write=False)
    monkeypatch.setattr("kimp3.executor.get_backend", lambda path: FakeBackend())
    monkeypatch.setattr(
        "kimp3.executor.cfg.collection.directory", str(tmp_path / "library")
    )
    monkeypatch.setattr(
        "kimp3.executor.cfg.paths.patterns.genre", "_Genres/%genre/%song_title.mp3"
    )

    result = OperationExecutor(dry_run=False, interactive=False).execute_audio_file(
        audio_file
    )

    assert result.as_tuple() == (1, 0, 0)
    assert planned_link.is_symlink()
    assert not stale_link.exists()


def test_operation_executor_accepts_existing_correct_genre_symlink(
    monkeypatch, tmp_path
):
    target = tmp_path / "library" / "Artist" / "song.mp3"
    link = tmp_path / "library" / "_Genres" / "Rock" / "song.mp3"
    target.parent.mkdir(parents=True)
    link.parent.mkdir(parents=True)
    target.write_bytes(b"audio")
    link.symlink_to(os.path.relpath(target, link.parent))
    audio_file = DummyAudioFile(
        target,
        target,
        link,
        requires_tag_write=False,
        operation=FileOperation.MOVE,
    )
    monkeypatch.setattr("kimp3.executor.get_backend", lambda path: FakeBackend())

    result = OperationExecutor(dry_run=False, interactive=False).execute_audio_file(
        audio_file
    )

    assert result.as_tuple() == (1, 0, 0)
    assert link.is_symlink()
    assert (link.parent / Path(link.readlink())).resolve() == target


def test_cleanup_collection_removes_broken_genre_symlink_and_empty_dirs(
    monkeypatch, tmp_path
):
    library = tmp_path / "library"
    broken_link = library / "_Genres" / "Rock" / "missing.mp3"
    empty_dir = library / "Artist" / "Empty Album"
    broken_link.parent.mkdir(parents=True)
    empty_dir.mkdir(parents=True)
    broken_link.symlink_to("../../Artist/Missing/missing.mp3")
    monkeypatch.setattr("kimp3.executor.cfg.collection.directory", str(library))
    monkeypatch.setattr(
        "kimp3.executor.cfg.paths.patterns.genre", "_Genres/%genre/%song_title.mp3"
    )
    monkeypatch.setattr("kimp3.executor.cfg.collection.clean_symlinks", True)
    monkeypatch.setattr("kimp3.executor.cfg.scan.delete_empty_dirs", True)
    monkeypatch.setattr("kimp3.executor.cfg.scan.junk_files", ["Thumbs.db"])

    OperationExecutor(dry_run=False, interactive=False).cleanup_collection([empty_dir])

    assert not broken_link.exists()
    assert not empty_dir.exists()


def test_cleanup_collection_removes_genre_symlink_to_loop(monkeypatch, tmp_path):
    library = tmp_path / "library"
    loop_target = library / "Artist" / "Album" / "loop.mp3"
    genre_link = library / "_Genres" / "Rock" / "loop.mp3"
    loop_target.parent.mkdir(parents=True)
    genre_link.parent.mkdir(parents=True)
    loop_target.symlink_to(loop_target)
    genre_link.symlink_to(os.path.relpath(loop_target, genre_link.parent))
    monkeypatch.setattr("kimp3.executor.cfg.collection.directory", str(library))
    monkeypatch.setattr(
        "kimp3.executor.cfg.paths.patterns.genre", "_Genres/%genre/%song_title.mp3"
    )
    monkeypatch.setattr("kimp3.executor.cfg.collection.clean_symlinks", True)
    monkeypatch.setattr("kimp3.executor.cfg.scan.delete_empty_dirs", False)
    monkeypatch.setattr("kimp3.executor.cfg.scan.junk_files", [])

    OperationExecutor(dry_run=False, interactive=False).cleanup_collection([library])

    assert loop_target.is_symlink()
    assert not genre_link.exists()


def test_cleanup_collection_removes_junk_before_empty_dir_cleanup(
    monkeypatch, tmp_path
):
    library = tmp_path / "library"
    album_dir = library / "Artist" / "Album"
    junk_file = album_dir / "Thumbs.db"
    album_dir.mkdir(parents=True)
    junk_file.write_bytes(b"junk")
    monkeypatch.setattr("kimp3.executor.cfg.collection.directory", str(library))
    monkeypatch.setattr("kimp3.executor.cfg.collection.clean_symlinks", False)
    monkeypatch.setattr("kimp3.executor.cfg.scan.delete_empty_dirs", True)
    monkeypatch.setattr("kimp3.executor.cfg.scan.junk_files", ["Thumbs.db"])

    OperationExecutor(dry_run=False, interactive=False).cleanup_collection([album_dir])

    assert not junk_file.exists()
    assert not album_dir.exists()


def test_cleanup_collection_dry_run_keeps_junk_and_directory(monkeypatch, tmp_path):
    library = tmp_path / "library"
    album_dir = library / "Artist" / "Album"
    junk_file = album_dir / "Thumbs.db"
    album_dir.mkdir(parents=True)
    junk_file.write_bytes(b"junk")
    monkeypatch.setattr("kimp3.executor.cfg.collection.directory", str(library))
    monkeypatch.setattr("kimp3.executor.cfg.collection.clean_symlinks", False)
    monkeypatch.setattr("kimp3.executor.cfg.scan.delete_empty_dirs", True)
    monkeypatch.setattr("kimp3.executor.cfg.scan.junk_files", ["Thumbs.db"])

    OperationExecutor(dry_run=True, interactive=False).cleanup_collection([album_dir])

    assert junk_file.exists()
    assert album_dir.exists()

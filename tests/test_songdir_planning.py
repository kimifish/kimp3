from pathlib import Path

from kimp3.models import AudioTags, FileOperation
from kimp3.planning import OperationPlan, PathPlan, build_tag_change_plan
from kimp3.songdir import SongDir


class DummyAudioFile:
    def __init__(self, path: Path, target: Path, title: str):
        self.filepath = path
        self.tags = AudioTags(title=title, artist="Artist", album_artist="Artist", track_number=1)
        self.recalculated = 0
        self.operation_plan = OperationPlan(
            path=PathPlan(source_path=path, target_path=target, operation=FileOperation.COPY),
            tags=build_tag_change_plan(self.tags, self.tags),
        )

    def calculate_new_paths_from_tags(self):
        self.recalculated += 1
        self.operation_plan = OperationPlan(
            path=PathPlan(source_path=self.filepath, target_path=self.operation_plan.path.target_path, operation=FileOperation.COPY),
            tags=build_tag_change_plan(AudioTags(), self.tags),
        )


def test_duplicate_track_number_clears_weaker_candidate(tmp_path):
    target_dir = tmp_path / "library" / "Artist" / "Album"
    stronger = tmp_path / "stronger.flac"
    weaker = tmp_path / "weaker.mp3"
    stronger.write_bytes(b"flac")
    weaker.write_bytes(b"mp3")
    strong_file = DummyAudioFile(stronger, target_dir / "01. Strong.flac", "Strong")
    weak_file = DummyAudioFile(weaker, target_dir / "01. Weak.mp3", "Weak")
    song_dir = object.__new__(SongDir)
    song_dir.audio_files = [strong_file, weak_file]

    SongDir._resolve_duplicate_track_numbers(song_dir)

    assert strong_file.tags.track_number == 1
    assert weak_file.tags.track_number is None
    assert weak_file.recalculated == 1
    assert any("Duplicate track number" in warning for warning in weak_file.operation_plan.warnings)

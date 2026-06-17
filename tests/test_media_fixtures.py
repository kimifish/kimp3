from pathlib import Path
import shutil

from kimp3.backends import Mp3Id3Backend, TagWritePolicy
from kimp3.executor import OperationExecutor
from kimp3.models import AudioTags, FileOperation
from kimp3.planning import OperationPlan, PathPlan, build_tag_change_plan


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "media"
SAMPLE_MP3 = FIXTURES_DIR / "sample.mp3"
SMALL_COVER = FIXTURES_DIR / "small-cover.jpg"
LARGE_COVER = FIXTURES_DIR / "large-cover.jpg"


class FixtureAudioFile:
    def __init__(self, source: Path, target: Path, target_tags: AudioTags, source_tags: AudioTags | None = None):
        self.filepath = source
        self.new_filepath = target
        self.operation_processed = FileOperation.NONE
        self.tag_write_success = False
        self.tags = target_tags
        self.operation_plan = OperationPlan(
            path=PathPlan(source_path=source, target_path=target, operation=FileOperation.COPY),
            tags=build_tag_change_plan(source_tags or AudioTags(), target_tags),
        )

    def write_tags(self) -> bool:
        Mp3Id3Backend().write(self.filepath, self.operation_plan.tags.target_tags, TagWritePolicy())
        return not Mp3Id3Backend().verify(self.filepath, self.operation_plan.tags.target_tags, TagWritePolicy())

    def print_changes(self, **kwargs):
        return None


def test_mp3_fixture_backend_write_read_verify(tmp_path):
    target = tmp_path / "sample.mp3"
    shutil.copyfile(SAMPLE_MP3, target)
    cover = SMALL_COVER.read_bytes()
    tags = AudioTags(
        title="Fixture Title",
        artist="Fixture Artist",
        album="Fixture Album",
        album_artist="Fixture Artist",
        track_number=1,
        total_tracks=9,
        year=2024,
        genre="Rock, Test",
        rating=80,
        album_cover=cover,
    )

    backend = Mp3Id3Backend()
    backend.write(target, tags, TagWritePolicy())
    read_tags = backend.read(target)

    assert read_tags.title == "Fixture Title"
    assert read_tags.artist == "Fixture Artist"
    assert read_tags.track_number == 1
    assert read_tags.total_tracks == 9
    assert read_tags.genres == ["Rock", "Test"]
    assert read_tags.rating == 80
    assert read_tags.album_cover == cover
    assert backend.verify(target, tags, TagWritePolicy()) == []


def test_executor_replace_existing_keeps_larger_existing_artwork(tmp_path):
    source = tmp_path / "incoming" / "source.mp3"
    target = tmp_path / "library" / "Artist" / "Song.mp3"
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    shutil.copyfile(SAMPLE_MP3, source)
    shutil.copyfile(SAMPLE_MP3, target)
    small_cover = SMALL_COVER.read_bytes()
    large_cover = LARGE_COVER.read_bytes()
    backend = Mp3Id3Backend()
    backend.write(
        target,
        AudioTags(title="Old", artist="Artist", album="Album", album_artist="Artist", album_cover=large_cover),
        TagWritePolicy(),
    )
    planned_tags = AudioTags(
        title="Song",
        artist="Artist",
        album="Album",
        album_artist="Artist",
        album_cover=small_cover,
    )
    audio_file = FixtureAudioFile(source, target, planned_tags)
    audio_file.operation_plan.replace_existing = True

    result = OperationExecutor(dry_run=False, interactive=False).execute_audio_file(audio_file)
    read_tags = backend.read(target)

    assert result.as_tuple() == (1, 0, 0)
    assert read_tags.title == "Song"
    assert read_tags.album_cover == large_cover
    assert len(read_tags.album_cover) > len(small_cover)


def test_executor_replace_existing_preserves_library_rating_and_lyrics(tmp_path):
    source = tmp_path / "incoming" / "source.mp3"
    target = tmp_path / "library" / "Artist" / "Song.mp3"
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    shutil.copyfile(SAMPLE_MP3, source)
    shutil.copyfile(SAMPLE_MP3, target)
    backend = Mp3Id3Backend()
    backend.write(
        target,
        AudioTags(
            title="Old",
            artist="Artist",
            album="Album",
            album_artist="Artist",
            rating=95,
            lyrics="Library lyrics",
        ),
        TagWritePolicy(),
    )
    planned_tags = AudioTags(
        title="Song",
        artist="Artist",
        album="Album",
        album_artist="Artist",
        rating=10,
        lyrics="Incoming lyrics",
    )
    audio_file = FixtureAudioFile(source, target, planned_tags)
    audio_file.operation_plan.replace_existing = True

    result = OperationExecutor(dry_run=False, interactive=False).execute_audio_file(audio_file)
    read_tags = backend.read(target)

    assert result.as_tuple() == (1, 0, 0)
    assert read_tags.title == "Song"
    assert read_tags.rating == 95
    assert read_tags.lyrics.text == "Library lyrics"

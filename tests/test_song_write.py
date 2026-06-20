from pathlib import Path

from kimp3.models import AudioTags, FileOperation
from kimp3.song import AudioFile


class FakeEasyID3(dict):
    deleted = False
    saved = False

    def __init__(self, path):
        super().__init__(
            {
                "title": ["Old"],
                "artist": ["Artist"],
                "album": ["Album"],
                "albumartist": ["Artist"],
            }
        )

    def delete(self):
        self.__class__.deleted = True
        raise AssertionError("EasyID3.delete() must not be called")

    def save(self):
        self.__class__.saved = True


class FakeID3(dict):
    instances = []

    def __init__(self, path, *args, **kwargs):
        super().__init__({"TXXX:Preserved": object(), "COMM:Other:eng": object()})
        self.path = path
        self.saved = False
        self.added = []
        self.__class__.instances.append(self)

    def getall(self, key):
        return []

    def add(self, frame):
        self.added.append(frame)
        self[f"{frame.FrameID}:{getattr(frame, 'desc', '')}:eng"] = frame

    def delall(self, frame_id):
        for key in list(self.keys()):
            if key == frame_id or key.startswith(f"{frame_id}:"):
                del self[key]

    def save(self, *args, **kwargs):
        self.saved = True


def test_managed_write_does_not_delete_unknown_frames(monkeypatch):
    FakeEasyID3.deleted = False
    FakeEasyID3.saved = False
    FakeID3.instances = []

    monkeypatch.setattr("kimp3.backends.EasyID3", FakeEasyID3)
    monkeypatch.setattr("kimp3.backends.ID3", FakeID3)
    monkeypatch.setattr(AudioFile, "verify_tags", lambda self: True)

    audio_file = object.__new__(AudioFile)
    audio_file._filepath = Path("/tmp/song.mp3")
    audio_file.tags = AudioTags(title="New", artist="Artist", album="Album", album_artist="Artist")

    assert audio_file.write_tags() is True
    assert FakeEasyID3.deleted is False
    assert FakeEasyID3.saved is False
    assert FakeID3.instances[-1].saved is True
    assert "TXXX:Preserved" in FakeID3.instances[-1]
    assert "COMM:Other:eng" in FakeID3.instances[-1]


def test_write_tags_can_skip_verify(monkeypatch):
    FakeID3.instances = []

    monkeypatch.setattr("kimp3.backends.ID3", FakeID3)
    monkeypatch.setattr("kimp3.song.cfg.scan.verify_after_write", False)
    monkeypatch.setattr(
        AudioFile,
        "verify_tags",
        lambda self: (_ for _ in ()).throw(AssertionError("verify_tags should not run")),
    )

    audio_file = object.__new__(AudioFile)
    audio_file._filepath = Path("/tmp/song.mp3")
    audio_file.tags = AudioTags(title="New", artist="Artist")

    assert audio_file.write_tags() is True


def test_skip_tag_write_when_managed_tags_match(monkeypatch, tmp_path):
    audio_file = object.__new__(AudioFile)
    audio_file._filepath = tmp_path / "library" / "Artist" / "song.mp3"
    audio_file.path = audio_file._filepath.parent
    audio_file.name = audio_file._filepath.name
    audio_file.song_dir = type("SongDir", (), {"is_compilation": False})()
    audio_file.tags = AudioTags(title="song", artist="Artist", album="Album", album_artist="Artist")
    audio_file.original_tags = AudioTags(title="song", artist="Artist", album="Album", album_artist="Artist")

    settings = type(
        "Cfg",
        (),
        {
            "collection": type("Collection", (), {"directory": str(tmp_path / "library"), "create_genre_links": False})(),
            "scan": type("Scan", (), {"operation": FileOperation.AUTO, "force_external_move": False})(),
            "paths": type(
                "Paths",
                (),
                {
                    "patterns": type(
                        "Patterns",
                        (),
                        {
                            "album": "%album_artist/%song_title.mp3",
                            "compilation": "%album_artist/%song_title.mp3",
                            "genre": "_Genres/%genre/%song_title.mp3",
                        },
                    )()
                },
            )(),
        },
    )()
    monkeypatch.setattr("kimp3.song.cfg", settings)

    audio_file.calculate_new_paths_from_tags()

    assert audio_file.skip_tag_write is True
    assert audio_file.operation_plan is not None
    assert audio_file.operation_plan.tags.requires_write is False


def test_operation_plan_marks_tag_write_when_tags_differ(monkeypatch, tmp_path):
    audio_file = object.__new__(AudioFile)
    audio_file._filepath = tmp_path / "library" / "Artist" / "song.mp3"
    audio_file.path = audio_file._filepath.parent
    audio_file.name = audio_file._filepath.name
    audio_file.song_dir = type("SongDir", (), {"is_compilation": False})()
    audio_file.tags = AudioTags(title="new", artist="Artist", album="Album", album_artist="Artist")
    audio_file.original_tags = AudioTags(title="old", artist="Artist", album="Album", album_artist="Artist")

    settings = type(
        "Cfg",
        (),
        {
            "collection": type("Collection", (), {"directory": str(tmp_path / "library"), "create_genre_links": False})(),
            "scan": type("Scan", (), {"operation": FileOperation.AUTO, "force_external_move": False})(),
            "paths": type(
                "Paths",
                (),
                {
                    "patterns": type(
                        "Patterns",
                        (),
                        {
                            "album": "%album_artist/%song_title.mp3",
                            "compilation": "%album_artist/%song_title.mp3",
                            "genre": "_Genres/%genre/%song_title.mp3",
                        },
                    )()
                },
            )(),
        },
    )()
    monkeypatch.setattr("kimp3.song.cfg", settings)

    audio_file.calculate_new_paths_from_tags()

    assert audio_file.skip_tag_write is False
    assert audio_file.operation_plan.tags.requires_write is True
    assert [change.field for change in audio_file.operation_plan.tags.changes] == ["title"]

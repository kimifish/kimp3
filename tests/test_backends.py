from datetime import date
from pathlib import Path

from kimp3.backends import FlacVorbisBackend, Mp3Id3Backend, TagWritePolicy, get_backend
from kimp3.models import AudioTags, LyricsLookup


class FakeFlac(dict):
    instances = []

    def __init__(self, path):
        super().__init__(
            {
                "title": ["Old"],
                "artist": ["Artist"],
                "album": ["Album"],
                "albumartist": ["Artist"],
                "tracknumber": ["1/9"],
                "genre": ["Rock"],
                "kimp3:lyrics_lookup": [
                    '{"status":"not_found","checked_at":"2026-06-18","artist":"Artist","title":"Old"}'
                ],
            }
        )
        self.path = path
        self.pictures = []
        self.saved = False
        self.__class__.instances.append(self)

    def save(self):
        self.saved = True


class FakeEasyId3(dict):
    instances = []

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.saved = False
        self.__class__.instances.append(self)

    def save(self):
        self.saved = True


class FakeId3(dict):
    instances = []

    def __init__(self, path, v2_version=None):
        super().__init__(
            {
                "APIC:Cover": object(),
                "USLT::eng": object(),
                "COMM::eng": object(),
                "COMM:Rating:eng": object(),
                "COMM:LastFM tags:eng": object(),
                "COMM:KiMP3 lyrics lookup:eng": object(),
            }
        )
        self.path = path
        self.v2_version = v2_version
        self.saved_version = None
        self.__class__.instances.append(self)

    def add(self, frame):
        self[f"{frame.FrameID}:{getattr(frame, 'desc', '')}:eng"] = frame

    def save(self, v2_version=None):
        self.saved_version = v2_version


def test_get_backend_returns_flac_backend():
    assert isinstance(get_backend(Path("song.flac")), FlacVorbisBackend)


def test_mp3_verify_reports_changed_fields(monkeypatch):
    backend = Mp3Id3Backend()
    monkeypatch.setattr(
        backend,
        "read",
        lambda path: AudioTags(title="Actual", artist="Artist", track_number=2),
    )

    errors = backend.verify(
        Path("song.mp3"),
        AudioTags(title="Expected", artist="Artist", track_number=None),
        TagWritePolicy(),
    )

    assert errors == [
        "Tag verification failed for song.mp3: title expected='Expected' actual='Actual'",
        "Tag verification failed for song.mp3: track_number expected=None actual=2",
    ]


def test_mp3_backend_removes_stale_managed_id3_frames(monkeypatch):
    FakeEasyId3.instances = []
    FakeId3.instances = []
    monkeypatch.setattr("kimp3.backends.EasyID3", FakeEasyId3)
    monkeypatch.setattr("kimp3.backends.ID3", FakeId3)

    Mp3Id3Backend().write(Path("song.mp3"), AudioTags(title="Song", artist="Artist"), TagWritePolicy())

    id3 = FakeId3.instances[-1]
    assert "APIC:Cover" not in id3
    assert "USLT::eng" not in id3
    assert "COMM::eng" not in id3
    assert "COMM:Rating:eng" not in id3
    assert "COMM:LastFM tags:eng" not in id3
    assert "COMM:KiMP3 lyrics lookup:eng" not in id3
    assert id3.saved_version == 3


def test_mp3_backend_writes_total_tracks_without_track_number(monkeypatch):
    FakeEasyId3.instances = []
    FakeId3.instances = []
    monkeypatch.setattr("kimp3.backends.EasyID3", FakeEasyId3)
    monkeypatch.setattr("kimp3.backends.ID3", FakeId3)

    Mp3Id3Backend().write(Path("song.mp3"), AudioTags(title="Song", artist="Artist", total_tracks=12), TagWritePolicy())

    easy_tags = FakeEasyId3.instances[-1]
    assert easy_tags["tracknumber"] == ["/12"]
    assert easy_tags.saved is True


def test_flac_backend_reads_vorbis_comments(monkeypatch):
    monkeypatch.setattr("kimp3.backends.FLAC", FakeFlac)

    tags = FlacVorbisBackend().read(Path("song.flac"))

    assert tags.title == "Old"
    assert tags.track_number == 1
    assert tags.total_tracks == 9
    assert tags.genres == ["Rock"]
    assert tags.lyrics_lookup is not None
    assert tags.lyrics_lookup.checked_at == date(2026, 6, 18)


def test_flac_backend_writes_managed_vorbis_comments(monkeypatch):
    monkeypatch.setattr("kimp3.backends.FLAC", FakeFlac)

    FlacVorbisBackend().write(
        Path("song.flac"),
        AudioTags(title="New", artist="Artist", album="Album", album_artist="Artist", genre="Jazz", rating=70),
        TagWritePolicy(),
    )

    flac = FakeFlac.instances[-1]
    assert flac["title"] == ["New"]
    assert flac["genre"] == ["Jazz"]
    assert flac["rating"] == ["70"]
    assert "kimp3:lyrics_lookup" not in flac
    assert flac.saved is True


def test_flac_backend_writes_lyrics_lookup_marker(monkeypatch):
    monkeypatch.setattr("kimp3.backends.FLAC", FakeFlac)

    FlacVorbisBackend().write(
        Path("song.flac"),
        AudioTags(
            title="New",
            artist="Artist",
            album="Album",
            album_artist="Artist",
            lyrics_lookup=LyricsLookup(checked_at=date(2026, 6, 18), artist="Artist", title="New"),
        ),
        TagWritePolicy(),
    )

    flac = FakeFlac.instances[-1]
    assert flac["kimp3:lyrics_lookup"] == [
        '{"status":"not_found","checked_at":"2026-06-18","artist":"Artist","title":"New"}'
    ]


def test_flac_backend_writes_total_tracks_without_track_number(monkeypatch):
    monkeypatch.setattr("kimp3.backends.FLAC", FakeFlac)

    FlacVorbisBackend().write(
        Path("song.flac"),
        AudioTags(title="New", artist="Artist", album="Album", album_artist="Artist", total_tracks=12),
        TagWritePolicy(),
    )

    flac = FakeFlac.instances[-1]
    assert "tracknumber" not in flac
    assert flac["tracktotal"] == ["12"]

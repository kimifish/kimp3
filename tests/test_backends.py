from pathlib import Path

from kimp3.backends import FlacVorbisBackend, TagWritePolicy, get_backend
from kimp3.models import AudioTags


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
            }
        )
        self.path = path
        self.pictures = []
        self.saved = False
        self.__class__.instances.append(self)

    def save(self):
        self.saved = True


def test_get_backend_returns_flac_backend():
    assert isinstance(get_backend(Path("song.flac")), FlacVorbisBackend)


def test_flac_backend_reads_vorbis_comments(monkeypatch):
    monkeypatch.setattr("kimp3.backends.FLAC", FakeFlac)

    tags = FlacVorbisBackend().read(Path("song.flac"))

    assert tags.title == "Old"
    assert tags.track_number == 1
    assert tags.total_tracks == 9
    assert tags.genres == ["Rock"]


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
    assert flac.saved is True

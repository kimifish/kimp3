from pathlib import Path

from kimp3.encoding import repair_audio_tags_text_encoding, repair_cp1251_mojibake
from kimp3.models import AudioTags
from kimp3.song import AudioFile


def mojibake_latin1(value: str) -> str:
    return value.encode("cp1251").decode("latin1")


def mojibake_utf8_as_cp1251(value: str) -> str:
    return value.encode("utf-8").decode("cp1251")


def test_repair_cp1251_bytes_decoded_as_latin1():
    assert repair_cp1251_mojibake(mojibake_latin1("Привет")) == "Привет"


def test_repair_utf8_bytes_decoded_as_cp1251():
    assert repair_cp1251_mojibake(mojibake_utf8_as_cp1251("Привет")) == "Привет"


def test_repair_does_not_change_normal_latin_text():
    assert repair_cp1251_mojibake("Smells Like Teen Spirit") == "Smells Like Teen Spirit"


def test_repair_audio_tags_text_fields():
    tags = AudioTags(
        title=mojibake_latin1("Песня"),
        artist=mojibake_latin1("Артист"),
        album="Album",
        genre=mojibake_latin1("Рок"),
        lyrics=mojibake_latin1("Текст песни"),
    )

    repaired = repair_audio_tags_text_encoding(tags)

    assert repaired.title == "Песня"
    assert repaired.artist == "Артист"
    assert repaired.album == "Album"
    assert repaired.genres == ["Рок"]
    assert repaired.lyrics.text == "Текст песни"


def test_audio_file_keeps_original_tags_and_repairs_target_tags(monkeypatch, tmp_path):
    raw_tags = AudioTags(title=mojibake_latin1("Песня"), artist="Artist")
    monkeypatch.setattr(AudioFile, "_read_tags", lambda self: raw_tags)
    song_dir = type("SongDir", (), {"track_count": 1})()

    audio_file = AudioFile(tmp_path / "song.mp3", song_dir)

    assert audio_file.original_tags.title == mojibake_latin1("Песня")
    assert audio_file.tags.title == "Песня"
    assert audio_file.tags_changed() is True

import pytest
from pathlib import Path
from kimp3.models import AudioTags, FileOperation, Lyrics, TrackNumber, UsualFile

class MockMutagenFile:
    """Mock класс для имитации mutagen.File"""
    def __init__(self, tags_dict=None):
        self.tags = MockEasyID3(tags_dict or {})

class MockEasyID3:
    """Mock класс для имитации EasyID3"""
    def __init__(self, tags_dict):
        self._tags = tags_dict

    def get(self, key, default=None):
        return self._tags.get(key, default)

@pytest.fixture
def complete_tags_dict():
    """Фикстура с полным набором тегов"""
    return {
        'title': ['Test Song'],
        'artist': ['Test Artist'],
        'album': ['Test Album'],
        'albumartist': ['Test Album Artist'],
        'tracknumber': ['5/12'],
        'discnumber': ['1/2'],
        'date': ['2023'],
        'genre': ['Rock']
    }

@pytest.fixture
def minimal_tags_dict():
    """Фикстура с минимальным набором тегов"""
    return {
        'title': ['Test Song'],
        'artist': ['Test Artist']
    }

class TestAudioTags:
    def test_create_empty_tags(self):
        """Тест создания пустого объекта AudioTags"""
        tags = AudioTags()
        assert tags.title == ""
        assert tags.artist == ""
        assert tags.album == ""
        assert tags.track_number is None
        assert isinstance(tags.track, TrackNumber)
        assert tags.year is None

    def test_from_mutagen_complete(self, complete_tags_dict):
        """Тест создания AudioTags из полного набора тегов"""
        mock_file = MockMutagenFile(complete_tags_dict)
        tags = AudioTags.from_mutagen(mock_file)

        assert tags.title == "Test Song"
        assert tags.artist == "Test Artist"
        assert tags.album == "Test Album"
        assert tags.album_artist == "Test Album Artist"
        assert tags.track_number == 5
        assert tags.total_tracks == 12
        assert tags.disc_number == 1
        assert tags.year == 2023
        assert tags.genre == "Rock"
        assert tags.genres == ["Rock"]

    def test_compilation_zero_is_false(self, minimal_tags_dict):
        tags_dict = minimal_tags_dict.copy()
        tags_dict['compilation'] = ['0']
        mock_file = MockMutagenFile(tags_dict)

        tags = AudioTags.from_mutagen(mock_file)

        assert tags.compilation is False

    def test_audio_tags_normalizes_lists_rating_and_lyrics(self):
        tags = AudioTags(genre="Rock, Pop", lastfm_tags="seen live, indie", rating="Rating: 80", lyrics=" words ")

        assert tags.genres == ["Rock", "Pop"]
        assert tags.lastfm_tags == ["seen live", "indie"]
        assert tags.rating == 80
        assert isinstance(tags.lyrics, Lyrics)
        assert tags.lyrics.text == "words"

    def test_from_mutagen_minimal(self, minimal_tags_dict):
        """Тест создания AudioTags из минимального набора тегов"""
        mock_file = MockMutagenFile(minimal_tags_dict)
        tags = AudioTags.from_mutagen(mock_file)

        assert tags.title == "Test Song"
        assert tags.artist == "Test Artist"
        assert tags.album == ""
        assert tags.track_number is None
        assert tags.total_tracks is None
        assert tags.disc_number is None
        assert tags.year is None
        assert tags.genre == ""

    def test_from_mutagen_none(self):
        """Тест создания AudioTags из None"""
        tags = AudioTags.from_mutagen(None)
        assert isinstance(tags, AudioTags)
        assert tags.title == ""
        assert tags.artist == ""

    @pytest.mark.parametrize("date_input,expected_year", [
        (['2023'], 2023),
        (['2023-05-15'], 2023),
        (['not a date'], None),
        ([''], None),
    ])
    def test_year_parsing(self, date_input, expected_year, minimal_tags_dict):
        """Тест различных форматов даты"""
        tags_dict = minimal_tags_dict.copy()
        tags_dict['date'] = date_input
        mock_file = MockMutagenFile(tags_dict)
        tags = AudioTags.from_mutagen(mock_file)
        assert tags.year == expected_year

    @pytest.mark.parametrize("track_input,expected_number,expected_total", [
        (['5/12'], 5, 12),
        (['5'], 5, None),
        (['0/0'], None, None),
        (['invalid'], None, None),
    ])
    def test_track_number_parsing(self, track_input, expected_number, expected_total, minimal_tags_dict):
        """Тест различных форматов номера трека"""
        tags_dict = minimal_tags_dict.copy()
        tags_dict['tracknumber'] = track_input
        mock_file = MockMutagenFile(tags_dict)
        tags = AudioTags.from_mutagen(mock_file)
        assert tags.track_number == expected_number
        assert tags.total_tracks == expected_total

class TestUsualFile:
    def test_create_usual_file(self):
        """Тест создания UsualFile"""
        path = Path("/test/path/song.mp3")
        usual_file = UsualFile(filepath=path, song_dir=None)

        assert usual_file.filepath == path
        assert usual_file.path == path.parent
        assert usual_file.name == path.name

    def test_set_new_filepath(self):
        """Тест установки нового пути"""
        path = Path("/test/path/song.mp3")
        new_path = Path("/new/path/song.mp3")
        usual_file = UsualFile(filepath=path, song_dir=None)
        usual_file.new_filepath = new_path

        assert usual_file.new_filepath == new_path
        assert usual_file.new_path == new_path.parent
        assert usual_file.new_name == new_path.name

class TestFileOperation:
    def test_file_operation_values(self):
        """Тест значений перечисления FileOperation"""
        assert FileOperation.COPY.value == "copy"
        assert FileOperation.MOVE.value == "move"
        assert FileOperation.NONE.value == "none"
        assert FileOperation.AUTO.value == "auto"

    def test_file_operation_comparison(self):
        """Тест сравнения значений FileOperation"""
        assert FileOperation.COPY != FileOperation.MOVE
        assert FileOperation.COPY == FileOperation.COPY

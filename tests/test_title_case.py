from kimp3.models import AudioTags
from kimp3.settings import TagsSettings
from kimp3.title_case import normalize_audio_tag_titles, normalize_title, sentence_case_safe, title_case_safe


def test_title_case_safe_normalizes_basic_english_titles():
    assert title_case_safe("the man who sold the world") == "The Man Who Sold the World"
    assert title_case_safe("there is a light that never goes out") == "There Is a Light That Never Goes Out"
    assert title_case_safe("wake me up before you go-go") == "Wake Me Up Before You Go-Go"
    assert title_case_safe("nothing but flowers") == "Nothing but Flowers"
    assert title_case_safe("in the court of the crimson king") == "In the Court of the Crimson King"


def test_title_case_safe_preserves_configured_exceptions_and_stylized_tokens():
    exceptions = ["AC/DC", "DJ", "deadmau5", "k.d. lang", "will.i.am"]

    assert title_case_safe("ac/dc", exceptions) == "AC/DC"
    assert title_case_safe("back in black by ac/dc", exceptions) == "Back in Black by AC/DC"
    assert title_case_safe("dj shadow", exceptions) == "DJ Shadow"
    assert title_case_safe("deadmau5", exceptions) == "deadmau5"
    assert title_case_safe("k.d. lang", exceptions) == "k.d. lang"
    assert title_case_safe("songs about girls by will.i.am", exceptions) == "Songs About Girls by will.i.am"


def test_sentence_case_safe_normalizes_cyrillic_titles():
    assert sentence_case_safe("группа крови") == "Группа крови"
    assert sentence_case_safe("ЗВЕЗДА ПО ИМЕНИ СОЛНЦЕ") == "Звезда по имени солнце"


def test_sentence_case_safe_preserves_russian_exceptions():
    exceptions = ["спЛин", "ДДТ", "АукцЫон", "Мумий Тролль"]

    assert sentence_case_safe("сплин - выхода нет", exceptions) == "спЛин - выхода нет"
    assert sentence_case_safe("ддт - что такое осень", exceptions) == "ДДТ - что такое осень"
    assert sentence_case_safe("аукцыон - дорога", exceptions) == "АукцЫон - дорога"
    assert sentence_case_safe("мумий тролль - владивосток 2000", exceptions) == "Мумий Тролль - владивосток 2000"


def test_normalize_title_keeps_mixed_scripts_except_exceptions():
    exceptions = ["ДДТ", "AC/DC", "спЛин"]

    assert normalize_title("ддт unplugged", "title_case_safe", exceptions) == "ДДТ unplugged"
    assert normalize_title("ac/dc на русском", "title_case_safe", exceptions) == "AC/DC на русском"
    assert normalize_title("сплин live", "title_case_safe", exceptions) == "спЛин live"
    assert normalize_title("mumiy troll владивосток 2000", "title_case_safe", exceptions) == "mumiy troll владивосток 2000"


def test_normalize_audio_tag_titles_does_not_touch_genres_or_lastfm_tags():
    tags = AudioTags(
        title="love is a long road",
        artist="tom petty",
        album="full moon fever",
        album_artist="tom petty",
        genres=["classic rock"],
        lastfm_tags=["heartland rock"],
    )

    normalized = normalize_audio_tag_titles(tags, TagsSettings())

    assert normalized.title == "Love Is a Long Road"
    assert normalized.artist == "Tom Petty"
    assert normalized.album == "Full Moon Fever"
    assert normalized.album_artist == "Tom Petty"
    assert normalized.genres == ["classic rock"]
    assert normalized.lastfm_tags == ["heartland rock"]


def test_normalize_audio_tag_titles_uses_russian_defaults():
    tags = AudioTags(
        title="ЗВЕЗДА ПО ИМЕНИ СОЛНЦЕ",
        artist="ддт",
        album="мумий тролль - морская",
        album_artist="сплин",
    )

    normalized = normalize_audio_tag_titles(tags, TagsSettings())

    assert normalized.title == "Звезда по имени солнце"
    assert normalized.artist == "ДДТ"
    assert normalized.album == "Мумий Тролль - морская"
    assert normalized.album_artist == "спЛин"

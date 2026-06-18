from kimp3 import tag_processing


class _FakeLastfmTag:
    def __init__(self, name, weight=100):
        self.weight = weight
        self.item = self
        self._name = name

    def get_name(self):
        return self._name


def test_get_llm_tags_uses_ai_server_v1_chat_contract(monkeypatch):
    calls = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "answer": '{"genres":["Rock","Dark Wave"],"tags":["Gothic","Moody"]}',
                "status": "ok",
            }

    def post(url, headers, json, timeout):
        calls["url"] = url
        calls["headers"] = headers
        calls["json"] = json
        calls["timeout"] = timeout
        return Response()

    monkeypatch.setattr(
        tag_processing.cfg.tags, "llm_url", "http://ai.local:8000/music_machine"
    )
    monkeypatch.setattr(tag_processing.cfg.tags, "llm_timeout", 45)
    monkeypatch.setattr(tag_processing.requests, "post", post)

    assert tag_processing.get_llm_tags("The Cure", "A Forest") == [
        "rock",
        "dark wave",
        "gothic",
        "moody",
    ]
    assert calls["url"] == "http://ai.local:8000/v1/chat"
    assert calls["headers"] == {"Content-Type": "application/json"}
    assert calls["timeout"] == 45

    payload = calls["json"]
    assert payload["message"] == "The Cure - A Forest"
    assert payload["thread_id"] == "vault_kimp3"
    assert payload["agent"] == "music_machine"
    assert payload["source"] == "kimp3"
    assert payload["actor_type"] == "program"
    assert payload["stream"] is False
    assert payload["include_reasoning"] is False
    assert payload["follow_up"] is False
    assert payload["metadata"]["ephemeral"] is True
    assert payload["metadata"]["skip_memory"] is True


def test_get_llm_tags_ignores_follow_up_ignored_status(monkeypatch):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"answer": "noise", "status": "ignored"}

    monkeypatch.setattr(
        tag_processing.cfg.tags, "llm_url", "http://ai.local:8000/v1/chat"
    )
    monkeypatch.setattr(
        tag_processing.requests, "post", lambda *args, **kwargs: Response()
    )

    assert tag_processing.get_llm_tags("Artist", "Title") == []


def test_get_llm_tags_parses_dict_answer_and_deduplicates(monkeypatch):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "answer": {
                    "genres": ["Rock", "Alternative Rock"],
                    "tags": ["Moody", "rock", "Layered Guitars"],
                },
                "status": "ok",
            }

    monkeypatch.setattr(
        tag_processing.cfg.tags, "llm_url", "http://ai.local:8000/v1/chat"
    )
    monkeypatch.setattr(
        tag_processing.requests, "post", lambda *args, **kwargs: Response()
    )

    assert tag_processing.get_llm_tags("Artist", "Title") == [
        "rock",
        "alternative rock",
        "moody",
        "layered guitars",
    ]


def test_get_llm_tags_parses_fenced_json_answer(monkeypatch):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "answer": '```json\n{"genres":["Synthwave"],"tags":["Retro","Nocturnal"]}\n```',
                "status": "ok",
            }

    monkeypatch.setattr(
        tag_processing.cfg.tags, "llm_url", "http://ai.local:8000/v1/chat"
    )
    monkeypatch.setattr(
        tag_processing.requests, "post", lambda *args, **kwargs: Response()
    )

    assert tag_processing.get_llm_tags("Artist", "Title") == [
        "synthwave",
        "retro",
        "nocturnal",
    ]


def test_process_lastfm_tags_keeps_single_tag_and_returns_lists(monkeypatch):
    monkeypatch.setattr(tag_processing.cfg.tags, "use_llm", False)
    monkeypatch.setattr(tag_processing.cfg.tags, "genres", ["rock"])
    monkeypatch.setattr(tag_processing.cfg.tags, "similar_tags", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "similar_tags_patterns", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_tags", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_tags_patterns", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_artists_from_tags", {})
    monkeypatch.setattr(tag_processing.cfg.tags, "max_length", 50)

    genres, tags = tag_processing.process_lastfm_tags(
        [], [], [_FakeLastfmTag("Rock")], artist_name="Artist", track_title="Title"
    )

    assert genres == ["rock"]
    assert tags == []


def test_process_lastfm_tags_aliases_before_genre_classification(monkeypatch):
    monkeypatch.setattr(tag_processing.cfg.tags, "use_llm", False)
    monkeypatch.setattr(tag_processing.cfg.tags, "genres", ["house"])
    monkeypatch.setattr(
        tag_processing.cfg.tags, "similar_tags", [["house", "house music"]]
    )
    monkeypatch.setattr(tag_processing.cfg.tags, "similar_tags_patterns", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_tags", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_tags_patterns", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_artists_from_tags", {})
    monkeypatch.setattr(tag_processing.cfg.tags, "max_length", 50)

    genres, tags = tag_processing.process_lastfm_tags(
        [],
        [],
        [_FakeLastfmTag("House Music")],
        artist_name="Artist",
        track_title="Title",
    )

    assert genres == ["house"]
    assert tags == []


def test_process_lastfm_tags_filters_banned_after_alias(monkeypatch):
    monkeypatch.setattr(tag_processing.cfg.tags, "use_llm", False)
    monkeypatch.setattr(tag_processing.cfg.tags, "genres", ["rock"])
    monkeypatch.setattr(
        tag_processing.cfg.tags, "similar_tags", [["rock", "rock music"]]
    )
    monkeypatch.setattr(tag_processing.cfg.tags, "similar_tags_patterns", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_tags", ["rock"])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_tags_patterns", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_artists_from_tags", {})
    monkeypatch.setattr(tag_processing.cfg.tags, "max_length", 50)

    genres, tags = tag_processing.process_lastfm_tags(
        [],
        [],
        [_FakeLastfmTag("Rock Music")],
        artist_name="Artist",
        track_title="Title",
    )

    assert genres == []
    assert tags == []


def test_process_lastfm_tags_llm_only_canonical_genre_can_be_selected(monkeypatch):
    monkeypatch.setattr(tag_processing.cfg.tags, "use_llm", True)
    monkeypatch.setattr(tag_processing.cfg.tags, "genres", ["dark wave"])
    monkeypatch.setattr(tag_processing.cfg.tags, "extended_genres", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "genre_parents", {})
    monkeypatch.setattr(tag_processing.cfg.tags, "similar_tags", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "similar_tags_patterns", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_tags", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_tags_patterns", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_artists_from_tags", {})
    monkeypatch.setattr(tag_processing.cfg.tags, "max_length", 50)
    monkeypatch.setattr(
        tag_processing,
        "get_llm_tag_suggestions",
        lambda artist, title: tag_processing.LlmTagSuggestions(
            ["dark wave"], ["gothic"]
        ),
    )

    genres, tags = tag_processing.process_lastfm_tags(
        [], [], [], artist_name="Artist", track_title="Title"
    )

    assert genres == ["dark wave"]
    assert tags == ["gothic"]


def test_process_lastfm_tags_confirmed_llm_only_genre_can_be_selected(monkeypatch):
    monkeypatch.setattr(tag_processing.cfg.tags, "use_llm", True)
    monkeypatch.setattr(tag_processing.cfg.tags, "genres", ["dark wave"])
    monkeypatch.setattr(tag_processing.cfg.tags, "extended_genres", ["dark wave"])
    monkeypatch.setattr(tag_processing.cfg.tags, "genre_parents", {})
    monkeypatch.setattr(tag_processing.cfg.tags, "similar_tags", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "similar_tags_patterns", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_tags", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_tags_patterns", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_artists_from_tags", {})
    monkeypatch.setattr(tag_processing.cfg.tags, "max_length", 50)
    monkeypatch.setattr(
        tag_processing,
        "get_llm_tag_suggestions",
        lambda artist, title: tag_processing.LlmTagSuggestions(
            ["dark wave"], ["gothic"]
        ),
    )

    genres, tags = tag_processing.process_lastfm_tags(
        [], [], [], artist_name="Artist", track_title="Title"
    )

    assert genres == ["dark wave"]
    assert tags == ["gothic"]


def test_process_lastfm_tags_llm_extended_genre_uses_canonical_parent(monkeypatch):
    monkeypatch.setattr(tag_processing.cfg.tags, "use_llm", True)
    monkeypatch.setattr(tag_processing.cfg.tags, "genres", ["dark wave"])
    monkeypatch.setattr(tag_processing.cfg.tags, "extended_genres", ["coldwave"])
    monkeypatch.setattr(
        tag_processing.cfg.tags, "genre_parents", {"coldwave": "dark wave"}
    )
    monkeypatch.setattr(tag_processing.cfg.tags, "similar_tags", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "similar_tags_patterns", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_tags", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_tags_patterns", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_artists_from_tags", {})
    monkeypatch.setattr(tag_processing.cfg.tags, "max_length", 50)
    monkeypatch.setattr(
        tag_processing,
        "get_llm_tag_suggestions",
        lambda artist, title: tag_processing.LlmTagSuggestions(["coldwave"], ["cold"]),
    )

    genres, tags = tag_processing.process_lastfm_tags(
        [], [], [], artist_name="Artist", track_title="Title"
    )

    assert genres == ["dark wave"]
    assert tags == ["coldwave", "cold"]


def test_process_lastfm_tags_lastfm_extended_genre_uses_canonical_parent(monkeypatch):
    monkeypatch.setattr(tag_processing.cfg.tags, "use_llm", False)
    monkeypatch.setattr(tag_processing.cfg.tags, "genres", ["dark wave"])
    monkeypatch.setattr(tag_processing.cfg.tags, "extended_genres", ["coldwave"])
    monkeypatch.setattr(
        tag_processing.cfg.tags, "genre_parents", {"coldwave": "dark wave"}
    )
    monkeypatch.setattr(tag_processing.cfg.tags, "similar_tags", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "similar_tags_patterns", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_tags", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_tags_patterns", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_artists_from_tags", {})
    monkeypatch.setattr(tag_processing.cfg.tags, "max_length", 50)

    genres, tags = tag_processing.process_lastfm_tags(
        [], [], [_FakeLastfmTag("Coldwave")], artist_name="Artist", track_title="Title"
    )

    assert genres == ["dark wave"]
    assert tags == ["coldwave"]


def test_process_lastfm_tags_post_punk_stays_post_punk(monkeypatch):
    monkeypatch.setattr(tag_processing.cfg.tags, "use_llm", False)
    monkeypatch.setattr(tag_processing.cfg.tags, "genres", ["post-punk", "punk"])
    monkeypatch.setattr(
        tag_processing.cfg.tags, "extended_genres", ["post-punk revival"]
    )
    monkeypatch.setattr(
        tag_processing.cfg.tags, "genre_parents", {"post-punk revival": "post-punk"}
    )
    monkeypatch.setattr(tag_processing.cfg.tags, "similar_tags", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "similar_tags_patterns", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_tags", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_tags_patterns", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_artists_from_tags", {})
    monkeypatch.setattr(tag_processing.cfg.tags, "max_length", 50)

    genres, tags = tag_processing.process_lastfm_tags(
        [], [], [_FakeLastfmTag("Post-Punk")], artist_name="Artist", track_title="Title"
    )

    assert genres == ["post-punk"]
    assert tags == []


def test_process_lastfm_tags_banned_artist_match_is_case_insensitive(monkeypatch):
    monkeypatch.setattr(tag_processing.cfg.tags, "use_llm", False)
    monkeypatch.setattr(tag_processing.cfg.tags, "genres", ["post-punk"])
    monkeypatch.setattr(tag_processing.cfg.tags, "extended_genres", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "genre_parents", {})
    monkeypatch.setattr(tag_processing.cfg.tags, "similar_tags", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "similar_tags_patterns", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_tags", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_tags_patterns", [])
    monkeypatch.setattr(
        tag_processing.cfg.tags, "banned_artists_from_tags", {"Post-Punk": ["ППВК"]}
    )
    monkeypatch.setattr(tag_processing.cfg.tags, "max_length", 50)

    genres, tags = tag_processing.process_lastfm_tags(
        [], [], [_FakeLastfmTag("Post-Punk")], artist_name="ппвк", track_title="Title"
    )

    assert genres == []
    assert tags == []


def test_process_lastfm_tags_post_punk_revival_maps_to_post_punk(monkeypatch):
    monkeypatch.setattr(tag_processing.cfg.tags, "use_llm", False)
    monkeypatch.setattr(tag_processing.cfg.tags, "genres", ["post-punk", "punk"])
    monkeypatch.setattr(
        tag_processing.cfg.tags, "extended_genres", ["post-punk revival"]
    )
    monkeypatch.setattr(
        tag_processing.cfg.tags, "genre_parents", {"post-punk revival": "post-punk"}
    )
    monkeypatch.setattr(tag_processing.cfg.tags, "similar_tags", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "similar_tags_patterns", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_tags", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_tags_patterns", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_artists_from_tags", {})
    monkeypatch.setattr(tag_processing.cfg.tags, "max_length", 50)

    genres, tags = tag_processing.process_lastfm_tags(
        [],
        [],
        [_FakeLastfmTag("Post-Punk Revival")],
        artist_name="Artist",
        track_title="Title",
    )

    assert genres == ["post-punk"]
    assert tags == ["post-punk revival"]


def test_process_lastfm_tags_preserves_existing_genre_and_tag_order(monkeypatch):
    monkeypatch.setattr(tag_processing.cfg.tags, "use_llm", False)
    monkeypatch.setattr(
        tag_processing.cfg.tags, "genres", ["dark wave", "post-punk", "rock"]
    )
    monkeypatch.setattr(tag_processing.cfg.tags, "similar_tags", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "similar_tags_patterns", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_tags", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_tags_patterns", [])
    monkeypatch.setattr(tag_processing.cfg.tags, "banned_artists_from_tags", {})
    monkeypatch.setattr(tag_processing.cfg.tags, "max_length", 50)

    genres, tags = tag_processing.process_lastfm_tags(
        [_FakeLastfmTag("Rock")],
        [_FakeLastfmTag("Post-Punk")],
        [_FakeLastfmTag("Moody"), _FakeLastfmTag("Dark Wave")],
        existing_genre="post-punk, rock",
        existing_tags="classic, moody",
        artist_name="Artist",
        track_title="Title",
    )

    assert genres == ["dark wave", "post-punk", "rock"]
    assert tags == ["moody", "classic"]

from kimp3 import musicbrainz


def test_get_artist_albums_fetches_release_groups(monkeypatch):
    calls = []

    def fake_get_json(path, params):
        calls.append((path, params))
        if path == "artist":
            return {"artists": [{"id": "beck-mbid", "name": "Beck"}]}
        return {
            "release-groups": [
                {"title": "The Information", "first-release-date": "2006-10-03"},
                {"title": "The Information", "first-release-date": "2006-10-03"},
                {"title": "Guero", "first-release-date": "2005-03-29"},
            ]
        }

    musicbrainz.clear_cache()
    monkeypatch.setattr(musicbrainz, "_get_json", fake_get_json)

    albums = musicbrainz.get_artist_albums("Beck")

    assert [album.title for album in albums] == ["The Information", "Guero"]
    assert albums[0].release_date == "2006-10-03"
    assert calls == [
        ("artist", {"query": 'artist:"Beck"', "limit": 5}),
        (
            "release-group",
            {"artist": "beck-mbid", "type": "album|ep", "limit": 100},
        ),
    ]


def test_get_artist_albums_prefers_specific_release_search(monkeypatch):
    calls = []

    def fake_get_json(path, params):
        calls.append((path, params))
        if path == "artist":
            return {"artists": [{"id": "beck-mbid", "name": "Beck"}]}
        if path == "release":
            return {
                "releases": [
                    {
                        "title": "The Information",
                        "disambiguation": "deluxe version",
                        "date": "2007",
                    }
                ]
            }
        return {"release-groups": [{"title": "The Information"}]}

    musicbrainz.clear_cache()
    monkeypatch.setattr(musicbrainz, "_get_json", fake_get_json)

    albums = musicbrainz.get_artist_albums(
        "Beck", "The Information (Deluxe Version)"
    )

    assert [album.title for album in albums] == [
        "The Information (Deluxe Version)",
        "The Information",
    ]
    assert calls == [
        (
            "release",
            {
                "query": 'artist:"Beck" AND release:"The Information"',
                "limit": 10,
            },
        ),
        ("artist", {"query": 'artist:"Beck"', "limit": 5}),
        (
            "release-group",
            {"artist": "beck-mbid", "type": "album|ep", "limit": 100},
        ),
    ]


def test_get_artist_albums_uses_cache(monkeypatch):
    musicbrainz.clear_cache()
    monkeypatch.setattr(
        musicbrainz,
        "_get_json",
        lambda path, params: (
            {"artists": [{"id": "id", "name": "Beck"}]}
            if path == "artist"
            else {"release-groups": [{"title": "Sea Change"}]}
        ),
    )

    assert [album.title for album in musicbrainz.get_artist_albums("Beck")] == [
        "Sea Change"
    ]
    monkeypatch.setattr(
        musicbrainz,
        "_get_json",
        lambda path, params: (_ for _ in ()).throw(AssertionError("cache miss")),
    )

    assert [album.title for album in musicbrainz.get_artist_albums("Beck")] == [
        "Sea Change"
    ]

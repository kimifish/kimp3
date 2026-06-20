from datetime import date, timedelta

import pylast

from kimp3 import lastfm
from kimp3.models import LyricsLookup
from kimp3.musicbrainz import AlbumCandidate


def test_init_lastfm_falls_back_to_unauthenticated_network(monkeypatch):
    calls = []

    class FakeNetwork:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            if kwargs.get("username"):
                raise pylast.PyLastError("login timeout")

    monkeypatch.setattr(lastfm.pylast, "LastFMNetwork", FakeNetwork)
    monkeypatch.setattr(lastfm.cfg.tags, "lastfm_api_key", "key")
    monkeypatch.setattr(lastfm.cfg.tags, "lastfm_api_secret", "secret")
    monkeypatch.setattr(lastfm.cfg.tags, "lastfm_username", "user")
    monkeypatch.setattr(lastfm.cfg.tags, "lastfm_password_hash", "hash")

    lastfm.init_lastfm()

    assert calls == [
        {
            "api_key": "key",
            "api_secret": "secret",
            "username": "user",
            "password_hash": "hash",
        },
        {"api_key": "key", "api_secret": "secret"},
    ]
    assert isinstance(lastfm.network, FakeNetwork)


def test_get_artist_albums_handles_pylast_base_errors(monkeypatch):
    class FakeArtist:
        def get_top_albums(self):
            raise pylast.PyLastError("network timeout")

    class FakeNetwork:
        @staticmethod
        def get_artist(artist_name):
            return FakeArtist()

    lastfm._artist_albums_cache.clear()
    monkeypatch.setattr(lastfm, "network", FakeNetwork())

    assert lastfm._get_artist_albums("Radiohead") == []


def test_lyrics_lookup_marker_skips_recent_retry(monkeypatch):
    monkeypatch.setattr(lastfm.cfg.tags, "lyrics_not_found_retry_days", 90)
    monkeypatch.setattr(lastfm.cfg.tags, "lyrics_not_found_retry_jitter_days", 0)
    lookup = LyricsLookup(
        checked_at=date.today() - timedelta(days=30), artist="Artist", title="Song"
    )

    assert lastfm._lyrics_lookup_is_fresh(lookup, "Artist", "Song") is True


def test_lyrics_lookup_marker_expires_after_retry_window(monkeypatch):
    monkeypatch.setattr(lastfm.cfg.tags, "lyrics_not_found_retry_days", 90)
    monkeypatch.setattr(lastfm.cfg.tags, "lyrics_not_found_retry_jitter_days", 0)
    lookup = LyricsLookup(
        checked_at=date.today() - timedelta(days=91), artist="Artist", title="Song"
    )

    assert lastfm._lyrics_lookup_is_fresh(lookup, "Artist", "Song") is False


def test_best_musicbrainz_album_match_weights_base_title(monkeypatch):
    calls = []

    def fake_get_artist_albums(artist, album_title=None):
        calls.append((artist, album_title))
        return [
            AlbumCandidate("Guero (Deluxe Edition)"),
            AlbumCandidate("The Information (Deluxe Version)"),
        ]

    monkeypatch.setattr(
        lastfm.musicbrainz,
        "get_artist_albums",
        fake_get_artist_albums,
    )

    match = lastfm._best_musicbrainz_album_match(
        "Beck", "The Information (Deluxe Edition)"
    )

    assert match is not None
    assert match[0] == "The Information (Deluxe Version)"
    assert calls == [("Beck", "The Information (Deluxe Edition)")]


def test_best_musicbrainz_album_match_keeps_specific_release_title(monkeypatch):
    monkeypatch.setattr(
        lastfm.musicbrainz,
        "get_artist_albums",
        lambda artist, album_title=None: [
            AlbumCandidate("The Information (Deluxe Version)"),
            AlbumCandidate("The Information"),
        ],
    )

    match = lastfm._best_musicbrainz_album_match(
        "Beck", "The Information (Deluxe Version)"
    )

    assert match is not None
    assert match[0] == "The Information (Deluxe Version)"


def test_best_lastfm_album_match_weights_base_title(monkeypatch):
    class FakeAlbum:
        def __init__(self, title):
            self.title = title

    class FakeTopItem:
        def __init__(self, title):
            self.item = FakeAlbum(title)

    monkeypatch.setattr(
        lastfm,
        "_get_artist_albums",
        lambda artist: [
            FakeTopItem("Guero (Deluxe Edition)"),
            FakeTopItem("The Information (Deluxe Version)"),
        ],
    )

    match = lastfm._best_lastfm_album_match("Beck", "The Information (Deluxe Edition)")

    assert match is not None
    assert match[0] == "The Information (Deluxe Version)"

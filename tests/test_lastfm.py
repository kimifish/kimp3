import pylast

from kimp3 import lastfm


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

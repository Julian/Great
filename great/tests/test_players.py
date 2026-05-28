from great.models import Item
from great.players import spotify_browser


def _song(spotify_uri: str | None = None) -> Item:
    return Item(
        id="x",
        kind="song",
        title="X",
        external_ids={"spotify": spotify_uri} if spotify_uri else {},
    )


def test_spotify_browser_rewrites_track_uri():
    item = _song("spotify:track:000N4CJL8IjQ0f2I4grgBO")
    assert (
        spotify_browser(item)
        == "https://open.spotify.com/track/000N4CJL8IjQ0f2I4grgBO"
    )


def test_spotify_browser_rewrites_album_uri():
    item = Item(
        id="x",
        kind="album",
        title="X",
        external_ids={"spotify": "spotify:album:abc123"},
    )
    assert spotify_browser(item) == "https://open.spotify.com/album/abc123"


def test_spotify_browser_returns_none_when_external_id_missing():
    assert spotify_browser(_song()) is None


def test_spotify_browser_returns_none_on_malformed_uri():
    assert spotify_browser(_song("not-a-spotify-uri")) is None
    assert spotify_browser(_song("spotify:track")) is None
    assert spotify_browser(_song("spotify:track:")) is None

"""
Map an :class:`~great.models.Item` to a URL where the user can play it.

A :data:`Player` is a callable taking an item and returning the URL to
hand to :mod:`webbrowser`, or ``None`` if it can't handle that item
(missing external id, unsupported kind, etc.). The ranking TUI's
open-in-player binding calls the configured player on the focused
item; only one is shipped today (:func:`spotify_browser`), but the
indirection is here so additional players (YouTube, Apple Music, ...)
can be added without touching the TUI.
"""

from collections.abc import Callable

from great.models import Item
from great.spotify import SOURCE_KEY as _SPOTIFY_SOURCE_KEY

__all__ = ["DEFAULT", "Player", "spotify_browser"]

Player = Callable[[Item], str | None]


def spotify_browser(item: Item) -> str | None:
    """
    Return the Spotify web-player URL for ``item``, or ``None``.

    Reads ``item.external_ids[SOURCE_KEY]`` (a ``spotify:<kind>:<id>``
    URI, as set by :mod:`great.spotify`) and rewrites it to
    ``https://open.spotify.com/<kind>/<id>`` — the form the web player
    opens and plays without requiring the desktop app.
    """
    uri = item.external_ids.get(_SPOTIFY_SOURCE_KEY)
    prefix = "spotify:"
    if not uri or not uri.startswith(prefix):
        return None
    kind, sep, ident = uri[len(prefix) :].partition(":")
    if not sep or not kind or not ident:
        return None
    return f"https://open.spotify.com/{kind}/{ident}"


DEFAULT: Player = spotify_browser

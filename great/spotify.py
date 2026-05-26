"""
Import a Spotify Extended Streaming History export as a provider source.

Spotify's privacy portal hands back a folder of
``Streaming_History_Audio_*.json`` files, each a JSON array of stream
events. :func:`read_export` walks that folder, dedupes events into the
unique tracks and albums it has seen and the per-day completed plays
the listener actually "consumed", and writes the result to
``sources/spotify.json``. :func:`provider_items` and
:func:`provider_log_entries` synthesize :class:`Item` and
:class:`LogEntry` records from that cache at compile/read time.

A track counts as consumed on a given day when at least one stream of
it that day either ran to ``reason_end == "trackdone"`` or played for
at least 30 seconds — Spotify's two complementary "this counted as a
listen" signals (the native completion marker and Wrapped's threshold).
Podcast and audiobook rows in the export are ignored: the engine has
no audiobook kind, and podcast plays don't carry enough metadata to
synthesize a useful catalog from here (use ``great import antennapod``
for that).
"""

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any
import json

from great.models import Item, LogEntry

SOURCE_KEY = "spotify"
CACHE_FILENAME = "spotify.json"

EXPORT_GLOB = "Streaming_History_Audio_*.json"

# Spotify Wrapped counts a play after 30 seconds; "trackdone" is the
# native completion signal. Their union catches both full plays and
# near-end plays the user manually moved on from.
_COMPLETED_MS_THRESHOLD = 30_000
_REASON_END_DONE = "trackdone"


class SpotifyError(Exception):
    """A Spotify import error."""


def read_export(path: Path) -> dict[str, Any]:
    """
    Parse a Spotify Extended Streaming History directory into the cache dict.

    Wraps :exc:`OSError` and JSON decode errors in :exc:`SpotifyError` so
    the CLI surfaces a clean message rather than a traceback.
    """
    if not path.is_dir():
        raise SpotifyError(f"no Spotify export directory at {path}")
    files = sorted(path.glob(EXPORT_GLOB))
    if not files:
        raise SpotifyError(
            f"no {EXPORT_GLOB} files found in {path}",
        )
    # Track metadata is gathered first with best-wins semantics
    # (null fields upgrade as later events supply them); album_id is
    # derived *after* the full sweep from each track's final best
    # (artist, album_name) pair. Doing it that way guarantees the
    # album set equals exactly what tracks reference — no orphans,
    # even when early events ship partial metadata that later
    # events complete.
    tracks: dict[str, dict[str, Any]] = {}
    # (track_uri, YYYY-MM-DD UTC) -> earliest qualifying ts that day.
    # Days are bucketed by the timestamp's UTC date — a 11pm-local play
    # may land in the next calendar day if the user's local timezone is
    # west of UTC. Acceptable: the export carries no local timezone,
    # and the day key is only used to collapse repeat-listens.
    completions: dict[tuple[str, str], str] = {}
    for f in files:
        try:
            data = json.loads(f.read_text())
        except (OSError, ValueError) as e:
            raise SpotifyError(f"could not read {f}: {e}") from e
        for event in data:
            track_uri = event.get("spotify_track_uri")
            if not track_uri:
                continue
            title = event.get("master_metadata_track_name") or track_uri
            artist = event.get("master_metadata_album_artist_name")
            album_name = event.get("master_metadata_album_album_name")
            existing = tracks.get(track_uri)
            if existing is None:
                tracks[track_uri] = {
                    "uri": track_uri,
                    "title": title,
                    "artist": artist,
                    "album_name": album_name,
                }
            else:
                if existing["artist"] is None and artist is not None:
                    existing["artist"] = artist
                if existing["album_name"] is None and album_name is not None:
                    existing["album_name"] = album_name
                if existing["title"] == track_uri and title != track_uri:
                    existing["title"] = title
            if not _counts_as_listen(event):
                continue
            ts = event["ts"]
            # ISO-8601 UTC timestamps sort lexicographically; the
            # ``[:10]`` prefix is the YYYY-MM-DD calendar day.
            key = (track_uri, ts[:10])
            existing_ts = completions.get(key)
            if existing_ts is None or ts < existing_ts:
                completions[key] = ts
    albums: dict[str, dict[str, Any]] = {}
    for track in tracks.values():
        album_name = track.pop("album_name")
        if not album_name:
            track["album_id"] = None
            continue
        aid = _album_id(track["artist"], album_name)
        track["album_id"] = aid
        if aid not in albums:
            albums[aid] = {
                "id": aid,
                "title": album_name,
                "artist": track["artist"],
            }
    return {
        "tracks": sorted(tracks.values(), key=lambda t: t["uri"]),
        "albums": sorted(albums.values(), key=lambda a: a["id"]),
        # The day key is derivable from ``ts[:10]``; only ``ts`` is
        # stored, and consumers reconstruct the day on the fly.
        "completions": [
            {"track_uri": uri, "ts": ts}
            for (uri, _day), ts in sorted(completions.items())
        ],
    }


def _album_id(artist: str | None, album: str | None) -> str:
    """
    Synthetic id for an album the streaming export doesn't URI-tag.

    The Extended Streaming History only ships the album *name* alongside
    the artist, so we mint a name-based id rather than invent a fake
    ``spotify:album:`` URI. Songs from a 1001albums-imported catalog
    (which do carry real Spotify album URIs) will not collide; they end
    up as separate album items rather than silently merging on a guess.
    """
    return f"spotify-name:{artist or ''}::{album or ''}"


def _counts_as_listen(event: dict[str, Any]) -> bool:
    if event.get("reason_end") == _REASON_END_DONE:
        return True
    return (event.get("ms_played") or 0) >= _COMPLETED_MS_THRESHOLD


def save_export(sources_dir: Path, data: dict[str, Any]) -> None:
    """Write the parsed export to ``sources/spotify.json``."""
    sources_dir.mkdir(parents=True, exist_ok=True)
    (sources_dir / CACHE_FILENAME).write_text(
        json.dumps(data, indent=2, sort_keys=True),
    )


def load_export(sources_dir: Path) -> dict[str, Any] | None:
    """Return the cached export, or ``None`` if not yet imported."""
    path = sources_dir / CACHE_FILENAME
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def counts(data: dict[str, Any]) -> tuple[int, int, int]:
    """Return ``(tracks, albums, completed_listen_days)`` for a brief."""
    return (
        len(data.get("tracks", [])),
        len(data.get("albums", [])),
        len(data.get("completions", [])),
    )


def provider_items(sources_dir: Path) -> Iterator[Item]:
    """Yield song and album items from the cached export."""
    data = load_export(sources_dir)
    if data is None:
        return
    for album in data.get("albums", []):
        yield _build_album(album)
    for track in data.get("tracks", []):
        yield _build_song(track)


def provider_log_entries(sources_dir: Path) -> Iterator[LogEntry]:
    """Yield ``consumed`` entries per (track, day) the user completed it."""
    data = load_export(sources_dir)
    if data is None:
        return
    for completion in data.get("completions", []):
        yield LogEntry(
            ts=datetime.fromisoformat(completion["ts"]),
            kind="song",
            item=completion["track_uri"],
            status="consumed",
        )


def _build_album(album: dict[str, Any]) -> Item:
    artist = album.get("artist")
    return Item(
        id=album["id"],
        kind="album",
        title=album["title"],
        creators=[artist] if artist else [],
    )


def _build_song(track: dict[str, Any]) -> Item:
    artist = track.get("artist")
    return Item(
        id=track["uri"],
        kind="song",
        title=track["title"],
        parent_id=track.get("album_id"),
        creators=[artist] if artist else [],
        external_ids={"spotify": track["uri"]},
    )

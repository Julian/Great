"""
Import a public 1001albumsgenerator.com project as a provider source.

The site exposes each user's project at
``https://1001albumsgenerator.com/api/v1/projects/<username>``.
:func:`fetch_project` retrieves it; :func:`save_project` writes the
raw JSON to ``sources/albumsgenerator.json`` in the data repo, where
the catalog compiler picks it up. :func:`provider_items` and
:func:`provider_log_entries` synthesize :class:`Item` and
:class:`LogEntry` records from the cache at compile/read time, so
re-importing is just a cache refresh.
"""

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
import json

import httpx

from great.models import Item, LogEntry

API_URL = "https://1001albumsgenerator.com/api/v1/projects/{username}"
SOURCE_KEY = "albumsgenerator"
CACHE_FILENAME = "albumsgenerator.json"


class AlbumsGeneratorError(Exception):
    """A 1001albums import error."""


class ProjectNotFoundError(AlbumsGeneratorError):
    """No public project for the given username."""


def fetch_project(
    username: str,
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """
    Fetch a public 1001albums project by username.

    Wraps :exc:`httpx.HTTPError` and JSON decode errors in
    :exc:`AlbumsGeneratorError` so the CLI surfaces a clean message
    rather than a traceback. A 404 specifically is surfaced as
    :exc:`ProjectNotFoundError`.
    """
    url = API_URL.format(username=username)
    try:
        if client is None:
            with httpx.Client(timeout=30.0) as c:
                resp = c.get(url)
        else:
            resp = client.get(url)
    except httpx.HTTPError as e:
        raise AlbumsGeneratorError(
            f"could not reach 1001albumsgenerator.com: {e}",
        ) from e
    if resp.status_code == httpx.codes.NOT_FOUND:
        raise ProjectNotFoundError(
            f"no 1001albums project for username {username!r}",
        )
    if resp.status_code >= httpx.codes.BAD_REQUEST:
        raise AlbumsGeneratorError(
            f"unexpected HTTP {resp.status_code} from 1001albumsgenerator.com",
        )
    try:
        return resp.json()
    except ValueError as e:
        raise AlbumsGeneratorError(
            f"invalid JSON from 1001albumsgenerator.com: {e}",
        ) from e


def save_project(sources_dir: Path, data: dict[str, Any]) -> None:
    """Write the raw project JSON to ``sources/albumsgenerator.json``."""
    sources_dir.mkdir(parents=True, exist_ok=True)
    (sources_dir / CACHE_FILENAME).write_text(
        json.dumps(data, indent=2, sort_keys=True),
    )


def load_project(sources_dir: Path) -> dict[str, Any] | None:
    """Return the cached project JSON, or ``None`` if not yet fetched."""
    path = sources_dir / CACHE_FILENAME
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def revealed_counts(data: dict[str, Any]) -> tuple[int, int]:
    """Return ``(revealed, unrevealed)`` history-entry counts."""
    history = data.get("history", [])
    revealed = sum(1 for e in history if e.get("revealedAlbum"))
    return revealed, len(history) - revealed


def provider_items(sources_dir: Path) -> Iterator[Item]:
    """Yield album items synthesized from the cached project."""
    data = load_project(sources_dir)
    if data is None:
        return
    for entry in data.get("history", []):
        if not entry.get("revealedAlbum"):
            continue
        yield _build_item(entry["album"])


def provider_log_entries(sources_dir: Path) -> Iterator[LogEntry]:
    """Yield ``consumed`` diary entries synthesized from the cached project."""
    data = load_project(sources_dir)
    if data is None:
        return
    for entry in data.get("history", []):
        if not entry.get("revealedAlbum"):
            continue
        item = _build_item(entry["album"])
        yield LogEntry(
            ts=datetime.fromisoformat(entry["generatedAt"]),
            kind="album",
            item=item.id,
            status="consumed",
            notes=_log_notes(entry),
        )


def _build_item(album: dict[str, Any]) -> Item:
    spotify_id = album.get("spotifyId")
    if spotify_id:
        item_id = f"spotify:album:{spotify_id}"
    else:
        item_id = f"1001albums:{album['uuid']}"
    external_ids: dict[str, str] = {"1001albums": album["uuid"]}
    if spotify_id:
        external_ids["spotify"] = f"spotify:album:{spotify_id}"
    for src, key in (
        ("apple_music", "appleMusicId"),
        ("tidal", "tidalId"),
        ("youtube_music", "youtubeMusicId"),
        ("qobuz", "qobuzId"),
        ("deezer", "deezerId"),
    ):
        value = album.get(key)
        if value:
            external_ids[src] = str(value)
    if album.get("wikipediaUrl"):
        slug = _wikipedia_slug(album["wikipediaUrl"])
        if slug:
            external_ids["wikipedia"] = slug
    return Item(
        id=item_id,
        kind="album",
        title=album["name"],
        year=_parse_year(album.get("releaseDate")),
        creators=[album["artist"]] if album.get("artist") else [],
        external_ids=external_ids,
    )


MAX_RATING = 5


def _log_notes(entry: dict[str, Any]) -> str | None:
    rating = entry.get("rating") or 0
    review = (entry.get("review") or "").strip()
    parts: list[str] = []
    if rating:
        parts.append("★" * rating + "☆" * (MAX_RATING - rating))
    if review:
        parts.append(review)
    return " — ".join(parts) if parts else None


YEAR_DIGITS = 4


def _parse_year(release_date: str | None) -> int | None:
    if not release_date or len(release_date) < YEAR_DIGITS:
        return None
    try:
        return int(release_date[:YEAR_DIGITS])
    except ValueError:
        return None


def _wikipedia_slug(url: str) -> str | None:
    parsed = urlparse(url)
    # Render hard-codes en.wikipedia.org/wiki/{slug}; non-English source
    # URLs would generate a broken English link, so reject them.
    if parsed.netloc != "en.wikipedia.org":
        return None
    prefix = "/wiki/"
    if not parsed.path.startswith(prefix):
        return None
    return unquote(parsed.path[len(prefix) :]) or None

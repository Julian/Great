"""
Import a public 1001albumsgenerator.com project into a Great store.

The site exposes each user's project at
``https://1001albumsgenerator.com/api/v1/projects/<username>``. Each
*revealed* history entry becomes an album item plus a ``consumed``
diary entry; unrevealed (upcoming) entries are skipped. Re-running the
importer is idempotent — existing items aren't duplicated, and log
entries are deduplicated by ``(kind, item, ts)``.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from great.models import Item, LogEntry
from great.store import Store

API_URL = "https://1001albumsgenerator.com/api/v1/projects/{username}"
SOURCE_KEY = "albumsgenerator"


class AlbumsGeneratorError(Exception):
    """A 1001albums import error."""


class ProjectNotFoundError(AlbumsGeneratorError):
    """No public project for the given username."""


@dataclass
class ImportResult:
    """Outcome of one :func:`import_project` call."""

    items_added: list[Item] = field(default_factory=list)
    items_existing: int = 0
    log_added: list[LogEntry] = field(default_factory=list)
    log_existing: int = 0
    skipped_unrevealed: int = 0


def fetch_project(
    username: str,
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Fetch a public 1001albums project by username."""
    url = API_URL.format(username=username)
    own_client = client is None
    c = client or httpx.Client(timeout=30.0)
    try:
        resp = c.get(url)
    finally:
        if own_client:
            c.close()
    if resp.status_code == httpx.codes.NOT_FOUND:
        raise ProjectNotFoundError(
            f"no 1001albums project for username {username!r}",
        )
    resp.raise_for_status()
    return resp.json()


def import_project(
    store: Store,
    data: dict[str, Any],
    *,
    dry_run: bool = False,
) -> ImportResult:
    """Merge a fetched 1001albums project into ``store``."""
    result = ImportResult()
    existing_log_keys = {(e.kind, e.item, e.ts) for e in store.log()}
    existing_item_ids = {i.id for i in store.items("album")}
    for entry in data.get("history", []):
        if not entry.get("revealedAlbum"):
            result.skipped_unrevealed += 1
            continue
        item = _build_item(entry["album"])
        if item.id in existing_item_ids:
            result.items_existing += 1
        else:
            if not dry_run:
                store.add_item(item)
            existing_item_ids.add(item.id)
            result.items_added.append(item)
        log_entry = _build_log_entry(item.id, entry)
        key = (log_entry.kind, log_entry.item, log_entry.ts)
        if key in existing_log_keys:
            result.log_existing += 1
        else:
            if not dry_run:
                store.append_log(log_entry)
            existing_log_keys.add(key)
            result.log_added.append(log_entry)
    return result


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
        external_ids=external_ids,
        metadata={"artist": album["artist"]},
    )


def _build_log_entry(item_id: str, entry: dict[str, Any]) -> LogEntry:
    return LogEntry(
        ts=datetime.fromisoformat(entry["generatedAt"]),
        kind="album",
        item=item_id,
        status="consumed",
        notes=_log_notes(entry),
    )


def _log_notes(entry: dict[str, Any]) -> str | None:
    rating = entry.get("rating") or 0
    review = (entry.get("review") or "").strip()
    parts: list[str] = []
    if rating:
        parts.append(f"{rating}/5")
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
    path = urlparse(url).path
    prefix = "/wiki/"
    if not path.startswith(prefix):
        return None
    return unquote(path[len(prefix) :]) or None

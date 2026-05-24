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
    items_promoted: list[Item] = field(default_factory=list)
    items_refreshed: list[Item] = field(default_factory=list)
    items_existing: int = 0
    log_added: list[LogEntry] = field(default_factory=list)
    log_existing: int = 0
    skipped_unrevealed: int = 0


def fetch_project(
    username: str,
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """
    Fetch a public 1001albums project by username.

    Wraps :exc:`httpx.HTTPError` (connection/timeout/etc.) and JSON
    decode errors in :exc:`AlbumsGeneratorError` so the CLI surfaces a
    clean message rather than a traceback. A 404 specifically is
    surfaced as :exc:`ProjectNotFoundError`.
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


def import_project(
    store: Store,
    data: dict[str, Any],
    *,
    dry_run: bool = False,
) -> ImportResult:
    """
    Merge a fetched 1001albums project into ``store``.

    Each revealed album is placed in the consumed catalog. If its id is
    already on the want queue, the want is dropped in favor of the
    imported item (mirroring ``great log --status consumed``). If the
    id is already in the catalog, source-controlled fields (title,
    year, importer-managed external_ids/metadata keys) are refreshed
    against the latest data; user-added external_ids and metadata keys
    are preserved.

    Changes are batched: items.toml and want.toml are each written at
    most once per import, and the log is appended only with new
    entries. Re-running with no upstream changes is a no-op.
    """
    result = ImportResult()
    existing_log_keys = {(e.kind, e.item, e.ts) for e in store.log()}
    existing_items = {i.id: i for i in store.items("album")}
    existing_wants = {w.id: w for w in store.wants("album")}

    merged_items: dict[str, Item] = dict(existing_items)
    wants_to_drop: set[str] = set()
    logs_to_append: list[LogEntry] = []
    seen_this_pass: set[str] = set()

    for entry in data.get("history", []):
        if not entry.get("revealedAlbum"):
            result.skipped_unrevealed += 1
            continue
        imported = _build_item(entry["album"])
        if imported.id not in seen_this_pass:
            if imported.id in existing_items:
                refreshed = _refreshed(existing_items[imported.id], imported)
                if refreshed != existing_items[imported.id]:
                    merged_items[imported.id] = refreshed
                    result.items_refreshed.append(refreshed)
                else:
                    result.items_existing += 1
            elif imported.id in existing_wants:
                merged_items[imported.id] = imported
                wants_to_drop.add(imported.id)
                result.items_promoted.append(imported)
            else:
                merged_items[imported.id] = imported
                result.items_added.append(imported)
            seen_this_pass.add(imported.id)

        log_entry = _build_log_entry(imported.id, entry)
        key = (log_entry.kind, log_entry.item, log_entry.ts)
        if key in existing_log_keys:
            result.log_existing += 1
        else:
            logs_to_append.append(log_entry)
            existing_log_keys.add(key)
            result.log_added.append(log_entry)

    if not dry_run:
        if merged_items != existing_items:
            store.write_items("album", list(merged_items.values()))
        if wants_to_drop:
            kept = [
                w for w in existing_wants.values() if w.id not in wants_to_drop
            ]
            store.write_wants("album", kept)
        for log_entry in logs_to_append:
            store.append_log(log_entry)
    return result


def summarize(result: ImportResult, *, dry_run: bool) -> str:
    """
    Format an :class:`ImportResult` as a single human-readable line.

    Zero-valued categories are elided so the common idempotent re-run
    reads as ``Up to date ...`` rather than a wall of zeros.
    """
    add = "Would add" if dry_run else "Added"
    add_lower = add.lower()
    refresh = "would refresh" if dry_run else "refreshed"
    promote = "would promote" if dry_run else "promoted"

    def _albums(n: int) -> str:
        return f"{n} album{'' if n == 1 else 's'}"

    clauses: list[str] = []
    if result.items_added:
        clauses.append(f"{add} {_albums(len(result.items_added))}")
    if result.items_refreshed:
        clauses.append(f"{refresh} {_albums(len(result.items_refreshed))}")
    if result.items_promoted:
        clauses.append(
            f"{promote} {_albums(len(result.items_promoted))} from want",
        )
    n_l = len(result.log_added)
    if n_l:
        verb = add if not clauses else add_lower
        word = "diary entry" if n_l == 1 else "diary entries"
        clauses.append(f"{verb} {n_l} {word}")

    if clauses:
        msg = ", ".join(clauses) + "."
    else:
        items_word = "album" if result.items_existing == 1 else "albums"
        log_word = "log entry" if result.log_existing == 1 else "log entries"
        msg = (
            f"Up to date — {result.items_existing} {items_word}, "
            f"{result.log_existing} {log_word}."
        )
    if result.skipped_unrevealed:
        msg += f" ({result.skipped_unrevealed} unrevealed skipped.)"
    return msg


def _refreshed(existing: Item, imported: Item) -> Item:
    """
    Overlay ``imported`` source-of-truth fields onto ``existing``.

    Title, year, and creators are taken from the import; external_ids
    and metadata dicts are merged with the import's values winning on
    key conflict (so user-added keys survive a re-import).
    """
    return Item(
        id=existing.id,
        kind=existing.kind,
        title=imported.title,
        year=imported.year,
        creators=imported.creators or existing.creators,
        external_ids={**existing.external_ids, **imported.external_ids},
        metadata={**existing.metadata, **imported.metadata},
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


def _build_log_entry(item_id: str, entry: dict[str, Any]) -> LogEntry:
    return LogEntry(
        ts=datetime.fromisoformat(entry["generatedAt"]),
        kind="album",
        item=item_id,
        status="consumed",
        notes=_log_notes(entry),
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

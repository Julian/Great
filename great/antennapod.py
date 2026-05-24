"""
Import an AntennaPod database export as a provider source.

AntennaPod's "Database export" (Settings → Import/Export) is a plain
SQLite file copied off-device. :func:`read_export` translates the
subset we care about — subscribed/kept feeds, played-or-favorited
episodes, and play-completion timestamps — into a JSON cache at
``sources/antennapod.json`` in the data repo. :func:`provider_items`
and :func:`provider_log_entries` synthesize :class:`Item` and
:class:`LogEntry` records from that cache at compile/read time.

Re-importing a fresh export overwrites the cache; ids are derived
from RSS-level identifiers (feed URL, ``<guid>``) so they stay stable
across exports.
"""

from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import json
import sqlite3

from great.models import Item, LogEntry

SOURCE_KEY = "antennapod"
CACHE_FILENAME = "antennapod.json"

# The PodDBAdapter schema version of current AntennaPod (3.11.x).
# Older exports may parse but with missing columns; the CLI warns when
# this differs from what the export reports.
EXPECTED_SCHEMA_VERSION = 3110000

# AntennaPod's `Feeds.state` enum. ``STATE_ARCHIVED`` rows are skipped;
# subscribed and unsubscribed-but-kept feeds are both surfaced so
# previously-played episodes still resolve to their parent podcast.
_STATE_SUBSCRIBED = 0
_STATE_NOT_SUBSCRIBED = 1
_STATE_ARCHIVED = 2

# `FeedItems.read`: -1 NEW, 0 UNPLAYED, 1 PLAYED.
_READ_PLAYED = 1


class AntennaPodError(Exception):
    """An AntennaPod import error."""


def read_export(path: Path) -> dict[str, Any]:
    """
    Parse an AntennaPod ``.db`` export into the cache dict.

    Wraps :exc:`sqlite3.Error` and missing-table/column errors in
    :exc:`AntennaPodError` so the CLI can surface a clean message.
    """
    if not path.is_file():
        raise AntennaPodError(f"no AntennaPod export at {path}")
    try:
        with closing(
            sqlite3.connect(f"file:{path}?mode=ro", uri=True),
        ) as conn:
            conn.row_factory = sqlite3.Row
            schema_version = conn.execute(
                "PRAGMA user_version",
            ).fetchone()[0]
            feeds_by_id = _read_feeds(conn)
            episodes = _read_episodes(conn, feeds_by_id)
    except sqlite3.Error as e:
        raise AntennaPodError(
            f"could not read AntennaPod export at {path}: {e}",
        ) from e
    return {
        "schema_version": schema_version,
        "feeds": list(feeds_by_id.values()),
        "episodes": episodes,
    }


def _read_feeds(conn: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    """Map AntennaPod's local feed-row id → cache feed dict (non-archived)."""
    rows = conn.execute(
        "SELECT id, download_url, feed_identifier, title, custom_title, "
        "author, image_url, state "
        "FROM Feeds "
        "WHERE state != ?",
        (_STATE_ARCHIVED,),
    ).fetchall()
    out: dict[int, dict[str, Any]] = {}
    for r in rows:
        feed_url = r["download_url"]
        if not feed_url:
            # Without a URL we have no stable id; skip rather than
            # invent one. Such rows are vanishingly rare in practice.
            continue
        out[r["id"]] = {
            "feed_url": feed_url,
            "feed_identifier": r["feed_identifier"] or None,
            "title": r["custom_title"] or r["title"] or feed_url,
            "author": r["author"] or None,
            "image_url": r["image_url"] or None,
            "state": r["state"],
        }
    return out


def _read_episodes(
    conn: sqlite3.Connection,
    feeds_by_id: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Played-or-favorited episodes for the kept feeds, as cache dicts."""
    # FeedMedia carries the FK back to FeedItems.id; ``FeedItems.media``
    # is unpopulated in current exports, so we join on the back-pointer
    # rather than the forward FK.
    rows = conn.execute(
        "SELECT "
        "  fi.feed AS feed_id, "
        "  fi.item_identifier, "
        "  fi.title, "
        "  fi.pubDate AS pub_date_ms, "
        "  fi.read, "
        "  fi.image_url AS image_url, "
        "  fm.duration AS duration_ms, "
        "  fm.playback_completion_date AS completed_at_ms, "
        "  CASE WHEN fav.feeditem IS NOT NULL THEN 1 ELSE 0 END "
        "    AS is_favorite "
        "FROM FeedItems fi "
        "LEFT JOIN FeedMedia fm ON fm.feeditem = fi.id "
        "LEFT JOIN Favorites fav ON fav.feeditem = fi.id "
        "WHERE fi.read = ? OR fav.feeditem IS NOT NULL",
        (_READ_PLAYED,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        feed = feeds_by_id.get(r["feed_id"])
        if feed is None:
            # Episode belongs to an archived feed we excluded.
            continue
        item_identifier = r["item_identifier"]
        if not item_identifier:
            # Fall back to a deterministic synthetic identifier so
            # reimports stay idempotent even without an RSS guid.
            item_identifier = _synthetic_episode_key(r)
        out.append(
            {
                "feed_url": feed["feed_url"],
                "parent_title": feed["title"],
                "item_identifier": item_identifier,
                "title": r["title"] or item_identifier,
                "pub_date_ms": r["pub_date_ms"] or None,
                "duration_ms": r["duration_ms"] or None,
                "image_url": r["image_url"] or None,
                "read": r["read"],
                "completed_at_ms": r["completed_at_ms"] or None,
                "is_favorite": bool(r["is_favorite"]),
            },
        )
    return out


def _synthetic_episode_key(row: sqlite3.Row) -> str:
    """Deterministic id for an episode missing an RSS guid."""
    return f"synthetic:{row['pub_date_ms'] or 0}:{row['title'] or ''}"


def save_export(sources_dir: Path, data: dict[str, Any]) -> None:
    """Write the parsed export to ``sources/antennapod.json``."""
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
    """Return ``(podcasts, episodes, completed)`` counts for a brief."""
    podcasts = len(data.get("feeds", []))
    episodes = data.get("episodes", [])
    completed = sum(
        1
        for e in episodes
        if e.get("read") == _READ_PLAYED and e.get("completed_at_ms")
    )
    return podcasts, len(episodes), completed


def provider_items(sources_dir: Path) -> Iterator[Item]:
    """Yield podcast and podcast_episode items from the cached export."""
    data = load_export(sources_dir)
    if data is None:
        return
    for feed in data.get("feeds", []):
        yield _build_podcast(feed)
    for episode in data.get("episodes", []):
        yield _build_episode(episode)


def provider_log_entries(sources_dir: Path) -> Iterator[LogEntry]:
    """Yield ``consumed`` diary entries for played-to-completion episodes."""
    data = load_export(sources_dir)
    if data is None:
        return
    feeds_by_url = {f["feed_url"]: f for f in data.get("feeds", [])}
    for episode in data.get("episodes", []):
        completed_ms = episode.get("completed_at_ms")
        if episode.get("read") != _READ_PLAYED or not completed_ms:
            continue
        if episode["feed_url"] not in feeds_by_url:
            continue
        yield LogEntry(
            ts=datetime.fromtimestamp(completed_ms / 1000, tz=UTC),
            kind="podcast_episode",
            item=_episode_id(episode["feed_url"], episode["item_identifier"]),
            status="consumed",
            notes="★ favorite" if episode.get("is_favorite") else None,
        )


def _build_podcast(feed: dict[str, Any]) -> Item:
    external_ids: dict[str, str] = {"feed_url": feed["feed_url"]}
    if feed.get("feed_identifier"):
        external_ids["feed_identifier"] = feed["feed_identifier"]
    metadata: dict[str, Any] = {}
    if feed.get("image_url"):
        metadata["image_url"] = feed["image_url"]
    return Item(
        id=feed["feed_url"],
        kind="podcast",
        title=feed["title"],
        creators=[feed["author"]] if feed.get("author") else [],
        external_ids=external_ids,
        metadata=metadata,
    )


def _build_episode(episode: dict[str, Any]) -> Item:
    feed_url = episode["feed_url"]
    guid = episode["item_identifier"]
    external_ids = {"feed_url": feed_url, "guid": guid}
    # The episode's publication year rarely helps when ranking, so we
    # leave Item.year unset and surface the parent show's title through
    # metadata instead so display paths can render it.
    metadata: dict[str, Any] = {}
    if episode.get("parent_title"):
        metadata["parent_title"] = episode["parent_title"]
    if episode.get("duration_ms"):
        metadata["duration_ms"] = episode["duration_ms"]
    if episode.get("image_url"):
        metadata["image_url"] = episode["image_url"]
    if episode.get("is_favorite"):
        metadata["favorite"] = True
    return Item(
        id=_episode_id(feed_url, guid),
        kind="podcast_episode",
        title=episode["title"],
        parent_id=feed_url,
        external_ids=external_ids,
        metadata=metadata,
    )


def _episode_id(feed_url: str, item_identifier: str) -> str:
    """Globally unique episode id within the ``podcast_episode`` kind."""
    return f"{feed_url}#{item_identifier}"

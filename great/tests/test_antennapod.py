"""Tests for the AntennaPod provider."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import json
import sqlite3

from typer.testing import CliRunner
import pytest

from great._cli import app
from great.antennapod import (
    CACHE_FILENAME,
    AntennaPodError,
    _episode_id,
    counts,
    load_export,
    provider_items,
    provider_log_entries,
    read_export,
    save_export,
)
from great.models import GreatConfig, ListConfig
from great.store import Store

# A handful of fixed timestamps so assertions stay readable. AntennaPod
# stores Date.getTime() in ms, UTC.
_PUB_2024 = int(datetime(2024, 3, 1, tzinfo=UTC).timestamp() * 1000)
_COMPLETED_2026 = int(
    datetime(2026, 4, 12, 18, 30, tzinfo=UTC).timestamp() * 1000,
)


# -- DB builder ----------------------------------------------------------


def _build_db(path: Path) -> sqlite3.Connection:
    """Create an empty AntennaPod-shaped SQLite DB at ``path``."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        PRAGMA user_version = 3110000;

        CREATE TABLE Feeds (
            id INTEGER PRIMARY KEY,
            download_url TEXT,
            feed_identifier TEXT,
            title TEXT,
            custom_title TEXT,
            author TEXT,
            image_url TEXT,
            state INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE FeedMedia (
            id INTEGER PRIMARY KEY,
            feeditem INTEGER NOT NULL,
            duration INTEGER,
            playback_completion_date INTEGER DEFAULT 0
        );

        CREATE TABLE FeedItems (
            id INTEGER PRIMARY KEY,
            feed INTEGER NOT NULL,
            item_identifier TEXT,
            title TEXT,
            pubDate INTEGER,
            read INTEGER NOT NULL DEFAULT 0,
            media INTEGER
        );

        CREATE TABLE Favorites (
            id INTEGER PRIMARY KEY,
            feeditem INTEGER NOT NULL
        );
        """,
    )
    conn.commit()
    return conn


def _insert_feed(
    conn: sqlite3.Connection,
    feed_id: int,
    *,
    url: str,
    title: str = "Show",
    author: str | None = None,
    state: int = 0,
    feed_identifier: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO Feeds "
        "(id, download_url, feed_identifier, title, author, state) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (feed_id, url, feed_identifier, title, author, state),
    )


def _insert_episode(
    conn: sqlite3.Connection,
    *,
    feeditem_id: int,
    feed_id: int,
    item_identifier: str | None,
    title: str,
    pub_date_ms: int | None = _PUB_2024,
    read: int = 0,
    duration_ms: int | None = 1_800_000,
    completed_at_ms: int = 0,
    favorite: bool = False,
) -> None:
    # Mirror real AntennaPod exports: FeedMedia carries the back-pointer
    # to FeedItems.id, while FeedItems.media is left NULL.
    if duration_ms is not None or completed_at_ms:
        conn.execute(
            "INSERT INTO FeedMedia "
            "(feeditem, duration, playback_completion_date) "
            "VALUES (?, ?, ?)",
            (feeditem_id, duration_ms, completed_at_ms),
        )
    conn.execute(
        "INSERT INTO FeedItems "
        "(id, feed, item_identifier, title, pubDate, read, media) "
        "VALUES (?, ?, ?, ?, ?, ?, NULL)",
        (
            feeditem_id,
            feed_id,
            item_identifier,
            title,
            pub_date_ms,
            read,
        ),
    )
    if favorite:
        conn.execute(
            "INSERT INTO Favorites (feeditem) VALUES (?)",
            (feeditem_id,),
        )


@pytest.fixture
def export_path(tmp_path):
    """A populated AntennaPod export covering the importer's branches."""
    path = tmp_path / "export.db"
    conn = _build_db(path)
    # Subscribed feed, played + completed episode (also favorited).
    _insert_feed(
        conn,
        1,
        url="https://example.com/feed.rss",
        title="The Example Show",
        author="Alice",
        feed_identifier="urn:atom:example",
    )
    _insert_episode(
        conn,
        feeditem_id=10,
        feed_id=1,
        item_identifier="guid-ep-1",
        title="Episode 1",
        read=1,
        completed_at_ms=_COMPLETED_2026,
        favorite=True,
    )
    # Same feed, played but no completion timestamp.
    _insert_episode(
        conn,
        feeditem_id=11,
        feed_id=1,
        item_identifier="guid-ep-2",
        title="Episode 2",
        read=1,
        completed_at_ms=0,
    )
    # Same feed, favorited but unplayed.
    _insert_episode(
        conn,
        feeditem_id=12,
        feed_id=1,
        item_identifier="guid-ep-3",
        title="Episode 3",
        read=0,
        favorite=True,
    )
    # Same feed, neither played nor favorited — should be skipped.
    _insert_episode(
        conn,
        feeditem_id=13,
        feed_id=1,
        item_identifier="guid-ep-4",
        title="Episode 4",
        read=0,
    )
    # Unsubscribed feed (state=1) with a played episode — kept.
    _insert_feed(
        conn,
        2,
        url="https://old.example.com/feed.rss",
        title="Old Show",
        state=1,
    )
    _insert_episode(
        conn,
        feeditem_id=20,
        feed_id=2,
        item_identifier="guid-old-1",
        title="Old Episode",
        read=1,
        completed_at_ms=_COMPLETED_2026 - 1_000_000,
    )
    # Archived feed (state=2) — should be excluded entirely.
    _insert_feed(
        conn,
        3,
        url="https://archived.example.com/feed.rss",
        title="Archived Show",
        state=2,
    )
    _insert_episode(
        conn,
        feeditem_id=30,
        feed_id=3,
        item_identifier="guid-archived-1",
        title="Should not appear",
        read=1,
        completed_at_ms=_COMPLETED_2026,
    )
    conn.commit()
    conn.close()
    return path


# -- Parser --------------------------------------------------------------


def test_read_export_includes_kept_feeds_and_excludes_archived(export_path):
    data = read_export(export_path)
    titles = {f["title"] for f in data["feeds"]}
    assert titles == {"The Example Show", "Old Show"}


def test_read_export_emits_played_or_favorited_episodes(export_path):
    data = read_export(export_path)
    identifiers = {e["item_identifier"] for e in data["episodes"]}
    # Episodes 1+2 (played) and 3 (favorited unplayed) from the kept feed,
    # plus the old-show played episode. Episode 4 (unplayed, unfavorited)
    # and the archived-feed episode are excluded.
    assert identifiers == {
        "guid-ep-1",
        "guid-ep-2",
        "guid-ep-3",
        "guid-old-1",
    }


def test_read_export_falls_back_to_synthetic_identifier(tmp_path):
    path = tmp_path / "no-guid.db"
    conn = _build_db(path)
    _insert_feed(conn, 1, url="https://example.com/feed.rss")
    _insert_episode(
        conn,
        feeditem_id=10,
        feed_id=1,
        item_identifier=None,
        title="Untitled",
        read=1,
        completed_at_ms=_COMPLETED_2026,
    )
    conn.commit()
    conn.close()
    data = read_export(path)
    assert data["episodes"][0]["item_identifier"].startswith("synthetic:")


def test_read_export_errors_when_file_missing(tmp_path):
    with pytest.raises(AntennaPodError, match="no AntennaPod export"):
        read_export(tmp_path / "missing.db")


def test_read_export_wraps_sqlite_errors(tmp_path):
    junk = tmp_path / "garbage.db"
    junk.write_text("not a sqlite file")
    with pytest.raises(AntennaPodError, match="could not read"):
        read_export(junk)


def test_counts_summarizes_played_and_completed(export_path):
    podcasts, episodes, completed = counts(read_export(export_path))
    assert (podcasts, episodes, completed) == (2, 4, 2)


# -- Cache I/O -----------------------------------------------------------


def test_save_and_load_roundtrip(tmp_path, export_path):
    data = read_export(export_path)
    save_export(tmp_path, data)
    assert (tmp_path / CACHE_FILENAME).is_file()
    assert load_export(tmp_path) == data


def test_load_returns_none_when_no_cache(tmp_path):
    assert load_export(tmp_path) is None


def test_provider_yields_nothing_when_no_cache(tmp_path):
    assert list(provider_items(tmp_path)) == []
    assert list(provider_log_entries(tmp_path)) == []


# -- Provider items & log entries ---------------------------------------


def test_provider_items_emit_podcasts_and_episodes(tmp_path, export_path):
    save_export(tmp_path, read_export(export_path))
    items = list(provider_items(tmp_path))
    podcasts = [i for i in items if i.kind == "podcast"]
    episodes = [i for i in items if i.kind == "podcast_episode"]
    assert {p.title for p in podcasts} == {"The Example Show", "Old Show"}
    assert {e.title for e in episodes} == {
        "Episode 1",
        "Episode 2",
        "Episode 3",
        "Old Episode",
    }


def test_provider_items_set_parent_id_to_feed_url(tmp_path, export_path):
    save_export(tmp_path, read_export(export_path))
    ep_1 = next(
        i
        for i in provider_items(tmp_path)
        if i.kind == "podcast_episode" and i.title == "Episode 1"
    )
    assert ep_1.parent_id == "https://example.com/feed.rss"
    assert ep_1.id == _episode_id(
        "https://example.com/feed.rss",
        "guid-ep-1",
    )
    assert ep_1.external_ids["guid"] == "guid-ep-1"
    # pub_date_ms is 2024-03-01 UTC, year is 2024.
    assert ep_1.year == 2024


def test_provider_items_carry_podcast_metadata(tmp_path, export_path):
    save_export(tmp_path, read_export(export_path))
    show = next(
        i
        for i in provider_items(tmp_path)
        if i.kind == "podcast" and i.title == "The Example Show"
    )
    assert show.id == "https://example.com/feed.rss"
    assert show.creators == ["Alice"]
    assert show.external_ids["feed_identifier"] == "urn:atom:example"


def test_provider_log_entries_only_for_completed_episodes(
    tmp_path,
    export_path,
):
    save_export(tmp_path, read_export(export_path))
    entries = list(provider_log_entries(tmp_path))
    # Episode 1 (played + completed + favorited) and Old Episode
    # (played + completed). Episode 2 is read but uncompleted, Episode 3
    # is favorited but unplayed.
    items = {e.item for e in entries}
    assert items == {
        _episode_id("https://example.com/feed.rss", "guid-ep-1"),
        _episode_id("https://old.example.com/feed.rss", "guid-old-1"),
    }
    favorite_entry = next(e for e in entries if e.item.endswith("guid-ep-1"))
    assert favorite_entry.notes == "★ favorite"
    assert favorite_entry.ts == datetime.fromtimestamp(
        _COMPLETED_2026 / 1000,
        tz=UTC,
    )
    assert all(e.kind == "podcast_episode" for e in entries)
    assert all(e.status == "consumed" for e in entries)


def test_reimport_overwrites_cache(tmp_path, export_path):
    save_export(tmp_path, read_export(export_path))
    first = json.loads((tmp_path / CACHE_FILENAME).read_text())
    save_export(tmp_path, read_export(export_path))
    second = json.loads((tmp_path / CACHE_FILENAME).read_text())
    assert first == second  # idempotent for the same input.


# -- Store integration ---------------------------------------------------


@pytest.fixture
def podcast_store(tmp_path):
    config = GreatConfig(
        lists=[
            ListConfig(name="podcasts", kind="podcast"),
            ListConfig(
                name="podcast_episodes",
                kind="podcast_episode",
            ),
        ],
    )
    return Store.init(tmp_path / "repo", config)


def test_provider_items_surface_via_store(podcast_store, export_path):
    save_export(podcast_store.sources_dir, read_export(export_path))
    podcasts = {p.title for p in podcast_store.items("podcast")}
    episodes = {e.title for e in podcast_store.items("podcast_episode")}
    assert podcasts == {"The Example Show", "Old Show"}
    assert "Episode 1" in episodes


def test_provider_log_entries_surface_via_store(podcast_store, export_path):
    save_export(podcast_store.sources_dir, read_export(export_path))
    entries = [e for e in podcast_store.log() if e.kind == "podcast_episode"]
    assert len(entries) == 2
    assert all(e.status == "consumed" for e in entries)


# -- CLI -----------------------------------------------------------------


def _make_store(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    Store.init(
        repo,
        GreatConfig(
            lists=[
                ListConfig(name="podcasts", kind="podcast"),
                ListConfig(
                    name="podcast_episodes",
                    kind="podcast_episode",
                ),
            ],
        ),
    )
    return repo


def test_cli_import_writes_cache(tmp_path, export_path):
    repo = _make_store(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(repo),
            "import",
            "antennapod",
            str(export_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Imported 2 podcasts and 4 episodes" in result.output
    assert (repo / "sources" / CACHE_FILENAME).is_file()


def test_cli_import_dry_run_does_not_write_cache(tmp_path, export_path):
    repo = _make_store(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(repo),
            "import",
            "antennapod",
            str(export_path),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Would import" in result.output
    assert not (repo / "sources" / CACHE_FILENAME).exists()


def test_cli_import_errors_when_file_missing(tmp_path):
    repo = _make_store(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(repo),
            "import",
            "antennapod",
            str(tmp_path / "nope.db"),
        ],
    )
    assert result.exit_code != 0
    assert "no AntennaPod export" in result.output


def test_cli_import_records_episode_in_diary(
    tmp_path: Path,
    export_path: Path,
) -> None:
    repo = _make_store(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(repo),
            "import",
            "antennapod",
            str(export_path),
        ],
    )
    assert result.exit_code == 0, result.output
    store = Store(repo)
    diary: list[Any] = [e for e in store.log() if e.kind == "podcast_episode"]
    assert len(diary) == 2

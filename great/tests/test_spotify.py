"""Tests for the Spotify Extended Streaming History provider."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import json

from typer.testing import CliRunner
import pytest

from great._cli import app
from great.models import GreatConfig, ListConfig
from great.spotify import (
    CACHE_FILENAME,
    SpotifyError,
    _album_id,
    counts,
    load_export,
    provider_items,
    provider_log_entries,
    read_export,
    save_export,
)
from great.store import Store

# -- Fixture builder ------------------------------------------------------


def _event(
    *,
    ts: str,
    track_uri: str | None = "spotify:track:abc",
    track: str | None = "Track A",
    artist: str | None = "Artist A",
    album: str | None = "Album A",
    ms_played: int = 200_000,
    reason_end: str = "trackdone",
    skipped: bool = False,
) -> dict[str, Any]:
    """Build a single Streaming_History_Audio_*.json event row."""
    return {
        "ts": ts,
        "platform": "osx",
        "ms_played": ms_played,
        "conn_country": "US",
        "ip_addr": "127.0.0.1",
        "master_metadata_track_name": track,
        "master_metadata_album_artist_name": artist,
        "master_metadata_album_album_name": album,
        "spotify_track_uri": track_uri,
        "episode_name": None,
        "episode_show_name": None,
        "spotify_episode_uri": None,
        "audiobook_title": None,
        "audiobook_uri": None,
        "audiobook_chapter_uri": None,
        "audiobook_chapter_title": None,
        "reason_start": "trackdone",
        "reason_end": reason_end,
        "shuffle": False,
        "skipped": skipped,
        "offline": False,
        "offline_timestamp": None,
        "incognito_mode": False,
    }


def _write_history(
    directory: Path,
    name: str,
    events: list[dict[str, Any]],
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(events))


@pytest.fixture
def export_dir(tmp_path: Path) -> Path:
    """A populated Spotify export covering the importer's branches."""
    directory = tmp_path / "spotify-export"
    _write_history(
        directory,
        "Streaming_History_Audio_2024.json",
        [
            # Track A: completed via trackdone. Two streams same day —
            # only the earliest qualifying ts should make it through.
            _event(ts="2024-01-01T08:00:00Z"),
            _event(ts="2024-01-01T07:00:00Z"),
            # Same track, different day → second (track, day) row.
            _event(ts="2024-01-02T09:00:00Z"),
            # Track B by a second artist: played < 30s and not
            # trackdone (skip). Catalogs the track and album but
            # emits no diary row.
            _event(
                ts="2024-01-03T10:00:00Z",
                track_uri="spotify:track:def",
                track="Track B",
                artist="Artist B",
                album="Album B",
                ms_played=5_000,
                reason_end="fwdbtn",
                skipped=True,
            ),
            # Track C: long play (>= 30s) but not trackdone. Should
            # still count as consumed via the ms_played threshold.
            _event(
                ts="2024-01-04T11:00:00Z",
                track_uri="spotify:track:ghi",
                track="Track C",
                artist="Artist A",
                album="Album A",
                ms_played=45_000,
                reason_end="endplay",
            ),
            # Missing track URI (pure podcast/garbage row) — skip.
            _event(
                ts="2024-01-05T12:00:00Z",
                track_uri=None,
                track=None,
                artist=None,
                album=None,
            ),
        ],
    )
    _write_history(
        directory,
        "Streaming_History_Audio_2025.json",
        [
            # Track A again, in the next-year file — still one item,
            # plus one more completion row for 2025-02-02.
            _event(ts="2025-02-02T13:00:00Z"),
        ],
    )
    return directory


# -- Parser ---------------------------------------------------------------


def test_read_export_dedupes_tracks_and_albums(export_dir):
    data = read_export(export_dir)
    track_uris = {t["uri"] for t in data["tracks"]}
    assert track_uris == {
        "spotify:track:abc",
        "spotify:track:def",
        "spotify:track:ghi",
    }
    album_titles = {a["title"] for a in data["albums"]}
    assert album_titles == {"Album A", "Album B"}


def test_read_export_collapses_completions_per_track_day(export_dir):
    data = read_export(export_dir)
    # Track A: 2024-01-01, 2024-01-02, 2025-02-02. Track C: 2024-01-04.
    # Track B never qualified.
    assert [(c["track_uri"], c["ts"][:10]) for c in data["completions"]] == [
        ("spotify:track:abc", "2024-01-01"),
        ("spotify:track:abc", "2024-01-02"),
        ("spotify:track:abc", "2025-02-02"),
        ("spotify:track:ghi", "2024-01-04"),
    ]
    # Two streams on 2024-01-01 → earliest ts wins.
    first = next(
        c
        for c in data["completions"]
        if c["track_uri"] == "spotify:track:abc"
        and c["ts"].startswith("2024-01-01")
    )
    assert first["ts"] == "2024-01-01T07:00:00Z"


def test_read_export_counts_listen_on_short_trackdone(tmp_path):
    # A trackdone play whose ms_played is below the 30s threshold still
    # counts: trackdone is Spotify's own "the track played through"
    # signal, and tracks shorter than 30s exist.
    directory = tmp_path / "short"
    _write_history(
        directory,
        "Streaming_History_Audio_2024.json",
        [
            _event(
                ts="2024-06-01T00:00:00Z",
                ms_played=15_000,
                reason_end="trackdone",
            ),
        ],
    )
    data = read_export(directory)
    assert len(data["completions"]) == 1


def test_read_export_upgrades_track_metadata_from_later_events(tmp_path):
    """
    A later event can fill in metadata a track was first seen without.

    Without this, an early "garbage" play (null artist / album) would
    permanently orphan the track from its album: subsequent events
    still register the album row, but no track ever parents to it.
    """
    directory = tmp_path / "upgrade"
    _write_history(
        directory,
        "Streaming_History_Audio_2024.json",
        [
            # First play: missing artist + album.
            _event(
                ts="2024-06-01T00:00:00Z",
                track_uri="spotify:track:xyz",
                track=None,
                artist=None,
                album=None,
            ),
            # Second play: full metadata. The track record should
            # absorb the artist + album linkage from this event.
            _event(
                ts="2024-06-02T00:00:00Z",
                track_uri="spotify:track:xyz",
                track="Real Title",
                artist="Real Artist",
                album="Real Album",
            ),
        ],
    )
    data = read_export(directory)
    [track] = data["tracks"]
    assert track["title"] == "Real Title"
    assert track["artist"] == "Real Artist"
    assert track["album_id"] == _album_id("Real Artist", "Real Album")
    # The album row exists AND a track parents to it — no orphan.
    [album] = data["albums"]
    parent_ids = {t["album_id"] for t in data["tracks"]}
    assert album["id"] in parent_ids


def test_read_export_has_no_orphan_albums_with_partial_metadata(tmp_path):
    """
    Even when artist arrives in a *later* event than album_name, the
    album row published in the cache matches what tracks parent to —
    no phantom 'spotify-name:::Album' alongside 'spotify-name:Artist::Album'.
    """
    directory = tmp_path / "partial"
    _write_history(
        directory,
        "Streaming_History_Audio_2024.json",
        [
            # First play has album name but no artist.
            _event(
                ts="2024-06-01T00:00:00Z",
                track_uri="spotify:track:xyz",
                track="Title",
                artist=None,
                album="Album X",
            ),
            # Second play fills in the artist.
            _event(
                ts="2024-06-02T00:00:00Z",
                track_uri="spotify:track:xyz",
                track="Title",
                artist="Artist Y",
                album="Album X",
            ),
        ],
    )
    data = read_export(directory)
    parent_ids = {t["album_id"] for t in data["tracks"]}
    album_ids = {a["id"] for a in data["albums"]}
    assert album_ids == parent_ids  # exact match → zero orphans
    assert album_ids == {_album_id("Artist Y", "Album X")}


def test_read_export_tolerates_null_artist_and_album(tmp_path):
    directory = tmp_path / "sparse"
    _write_history(
        directory,
        "Streaming_History_Audio_2024.json",
        [
            _event(
                ts="2024-06-01T00:00:00Z",
                track_uri="spotify:track:local",
                track="Local File",
                artist=None,
                album=None,
            ),
        ],
    )
    data = read_export(directory)
    # Track is cataloged; no album row is invented from null metadata.
    assert len(data["tracks"]) == 1
    assert data["tracks"][0]["album_id"] is None
    assert data["albums"] == []


def test_read_export_errors_when_directory_missing(tmp_path):
    with pytest.raises(SpotifyError, match="no Spotify export directory"):
        read_export(tmp_path / "missing")


def test_read_export_errors_when_no_history_files(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SpotifyError, match="no Streaming_History_Audio"):
        read_export(empty)


def test_read_export_wraps_json_errors(tmp_path):
    directory = tmp_path / "bad"
    directory.mkdir()
    (directory / "Streaming_History_Audio_2024.json").write_text("not json")
    with pytest.raises(SpotifyError, match="could not read"):
        read_export(directory)


def test_counts_returns_tracks_albums_completions(export_dir):
    tracks, albums, completions = counts(read_export(export_dir))
    assert (tracks, albums, completions) == (3, 2, 4)


# -- Cache I/O -----------------------------------------------------------


def test_save_and_load_roundtrip(tmp_path, export_dir):
    data = read_export(export_dir)
    save_export(tmp_path, data)
    assert (tmp_path / CACHE_FILENAME).is_file()
    assert load_export(tmp_path) == data


def test_load_returns_none_when_no_cache(tmp_path):
    assert load_export(tmp_path) is None


def test_provider_yields_nothing_when_no_cache(tmp_path):
    assert list(provider_items(tmp_path)) == []
    assert list(provider_log_entries(tmp_path)) == []


# -- Provider items & log entries ---------------------------------------


def test_provider_items_emit_songs_and_albums(tmp_path, export_dir):
    save_export(tmp_path, read_export(export_dir))
    items = list(provider_items(tmp_path))
    songs = {i.title: i for i in items if i.kind == "song"}
    albums = {i.title: i for i in items if i.kind == "album"}
    assert set(songs) == {"Track A", "Track B", "Track C"}
    assert set(albums) == {"Album A", "Album B"}


def test_provider_song_sets_parent_id_to_album(tmp_path, export_dir):
    save_export(tmp_path, read_export(export_dir))
    track_a = next(
        i
        for i in provider_items(tmp_path)
        if i.kind == "song" and i.title == "Track A"
    )
    assert track_a.id == "spotify:track:abc"
    assert track_a.parent_id == _album_id("Artist A", "Album A")
    assert track_a.creators == ["Artist A"]
    assert track_a.external_ids["spotify"] == "spotify:track:abc"


def test_provider_album_carries_creator(tmp_path, export_dir):
    save_export(tmp_path, read_export(export_dir))
    album_a = next(
        i
        for i in provider_items(tmp_path)
        if i.kind == "album" and i.title == "Album A"
    )
    assert album_a.creators == ["Artist A"]
    assert album_a.id == _album_id("Artist A", "Album A")


def test_provider_log_entries_one_per_track_day(tmp_path, export_dir):
    save_export(tmp_path, read_export(export_dir))
    entries = list(provider_log_entries(tmp_path))
    assert len(entries) == 4
    assert all(e.kind == "song" for e in entries)
    assert all(e.status == "consumed" for e in entries)
    track_a_2024_01_01 = next(
        e
        for e in entries
        if e.item == "spotify:track:abc"
        and e.ts.date().isoformat() == "2024-01-01"
    )
    assert track_a_2024_01_01.ts == datetime(2024, 1, 1, 7, 0, tzinfo=UTC)


def test_reimport_overwrites_cache(tmp_path, export_dir):
    save_export(tmp_path, read_export(export_dir))
    first = json.loads((tmp_path / CACHE_FILENAME).read_text())
    save_export(tmp_path, read_export(export_dir))
    second = json.loads((tmp_path / CACHE_FILENAME).read_text())
    assert first == second  # idempotent for the same input.


def test_reimport_with_more_history_strictly_extends_diary(tmp_path):
    """
    A later export with strictly more events extends the catalog and
    diary — existing items keep stable ids, existing completions keep
    their original timestamps, and new entries are exactly the events
    that were added.
    """
    directory = tmp_path / "export"
    cache = tmp_path / "cache"
    _write_history(
        directory,
        "Streaming_History_Audio_2024.json",
        [_event(ts="2024-01-01T07:00:00Z")],
    )
    save_export(cache, read_export(directory))
    initial_entries = {(e.item, e.ts) for e in provider_log_entries(cache)}
    initial_song_ids = {
        i.id for i in provider_items(cache) if i.kind == "song"
    }

    # Later: the user re-exports with more history. The 2024 file is
    # unchanged; a 2025 file has been added with a fresh play of the
    # existing track AND an entirely new track.
    _write_history(
        directory,
        "Streaming_History_Audio_2025.json",
        [
            _event(ts="2025-02-02T13:00:00Z"),
            _event(
                ts="2025-02-02T14:00:00Z",
                track_uri="spotify:track:new",
                track="New Track",
                artist="New Artist",
                album="New Album",
            ),
        ],
    )
    save_export(cache, read_export(directory))
    final_entries = {(e.item, e.ts) for e in provider_log_entries(cache)}
    final_song_ids = {i.id for i in provider_items(cache) if i.kind == "song"}

    # Strict-subset relationships: nothing from the first import got
    # dropped or had its timestamp shifted.
    assert initial_entries < final_entries
    assert initial_song_ids < final_song_ids
    # The delta is exactly the two events that were added.
    assert final_entries - initial_entries == {
        ("spotify:track:abc", datetime(2025, 2, 2, 13, 0, tzinfo=UTC)),
        ("spotify:track:new", datetime(2025, 2, 2, 14, 0, tzinfo=UTC)),
    }
    assert final_song_ids - initial_song_ids == {"spotify:track:new"}


# -- Store integration ---------------------------------------------------


@pytest.fixture
def music_store(tmp_path):
    config = GreatConfig(
        lists=[
            ListConfig(name="songs", kind="song"),
            ListConfig(name="albums", kind="album"),
            ListConfig(name="artists", kind="artist"),
        ],
    )
    return Store.init(tmp_path / "repo", config)


def test_provider_items_surface_via_store(music_store, export_dir):
    save_export(music_store.sources_dir, read_export(export_dir))
    songs = {s.title for s in music_store.items("song")}
    albums = {a.title for a in music_store.items("album")}
    artists = {a.title for a in music_store.items("artist")}
    assert songs == {"Track A", "Track B", "Track C"}
    assert albums == {"Album A", "Album B"}
    # Artists are auto-synthesized from song.creators by Store.compile.
    assert artists == {"Artist A", "Artist B"}


def test_provider_log_entries_surface_via_store(music_store, export_dir):
    save_export(music_store.sources_dir, read_export(export_dir))
    song_log = [e for e in music_store.log() if e.kind == "song"]
    assert len(song_log) == 4


# -- CLI -----------------------------------------------------------------


def _make_store(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    Store.init(
        repo,
        GreatConfig(
            lists=[
                ListConfig(name="songs", kind="song"),
                ListConfig(name="albums", kind="album"),
                ListConfig(name="artists", kind="artist"),
            ],
        ),
    )
    return repo


def test_cli_import_writes_cache(tmp_path, export_dir):
    repo = _make_store(tmp_path)
    result = CliRunner().invoke(
        app,
        ["--root", str(repo), "import", "spotify", str(export_dir)],
    )
    assert result.exit_code == 0, result.output
    assert "Imported 3 tracks and 2 albums" in result.output
    assert "(4 completed listening days)" in result.output
    assert (repo / "sources" / CACHE_FILENAME).is_file()


def test_cli_import_dry_run_does_not_write_cache(tmp_path, export_dir):
    repo = _make_store(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(repo),
            "import",
            "spotify",
            str(export_dir),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Would import" in result.output
    assert not (repo / "sources" / CACHE_FILENAME).exists()


def test_cli_import_errors_when_directory_missing(tmp_path):
    repo = _make_store(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(repo),
            "import",
            "spotify",
            str(tmp_path / "nope"),
        ],
    )
    assert result.exit_code != 0
    assert "no Spotify export directory" in result.output


def test_cli_import_records_song_in_diary(
    tmp_path: Path,
    export_dir: Path,
) -> None:
    repo = _make_store(tmp_path)
    result = CliRunner().invoke(
        app,
        ["--root", str(repo), "import", "spotify", str(export_dir)],
    )
    assert result.exit_code == 0, result.output
    store = Store(repo)
    diary: list[Any] = [e for e in store.log() if e.kind == "song"]
    assert len(diary) == 4

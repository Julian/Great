"""Tests for the 1001albums importer."""

from typing import Any
from unittest.mock import patch

from typer.testing import CliRunner
import pytest

from great._cli import app
from great.albumsgenerator import (
    ImportResult,
    ProjectNotFoundError,
    _build_item,
    _log_notes,
    _parse_year,
    _wikipedia_slug,
    import_project,
    summarize,
)
from great.models import GreatConfig, ListConfig
from great.store import Store


def _album(**overrides: Any) -> dict[str, Any]:
    base = {
        "uuid": "uuid-tlc",
        "artist": "TLC",
        "name": "Crazysexycool",
        "releaseDate": "1994",
        "spotifyId": "5eg56dCpFn32neJak2vk0f",
        "appleMusicId": "270246704",
        "tidalId": 667700,
        "wikipediaUrl": "https://en.wikipedia.org/wiki/CrazySexyCool",
    }
    base.update(overrides)
    return base


def _entry(**overrides: Any) -> dict[str, Any]:
    base = {
        "generatedAlbumId": "gen-1",
        "album": _album(),
        "rating": 4,
        "review": "",
        "revealedAlbum": True,
        "generatedAt": "2025-06-26T03:01:04.115Z",
    }
    base.update(overrides)
    return base


def _project(history: list[dict[str, Any]]) -> dict[str, Any]:
    return {"name": "user", "history": history}


@pytest.fixture
def albums_store(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="albums", kind="album")])
    return Store.init(tmp_path, config)


def test_parse_year_handles_yyyy_and_iso():
    assert _parse_year("1994") == 1994
    assert _parse_year("1994-05-01") == 1994


def test_parse_year_returns_none_for_garbage():
    assert _parse_year(None) is None
    assert _parse_year("") is None
    assert _parse_year("???") is None


def test_log_notes_combines_rating_and_review():
    assert _log_notes({"rating": 4, "review": ""}) == "★★★★☆"
    assert _log_notes({"rating": 0, "review": "loved it"}) == "loved it"
    assert _log_notes({"rating": 5, "review": "wow"}) == "★★★★★ — wow"
    assert _log_notes({"rating": 1, "review": ""}) == "★☆☆☆☆"
    assert _log_notes({"rating": 0, "review": ""}) is None
    assert _log_notes({}) is None


def test_wikipedia_slug_extracts_path():
    url = "https://en.wikipedia.org/wiki/Live!_(Fela_Kuti_album)"
    assert _wikipedia_slug(url) == "Live!_(Fela_Kuti_album)"


def test_wikipedia_slug_returns_none_for_non_wiki():
    assert _wikipedia_slug("https://example.com/foo") is None


def test_wikipedia_slug_rejects_non_english_wikipedia():
    # render.py hardcodes en.wikipedia.org; foreign-language URLs would
    # become broken English links if we stripped the path and stored it.
    assert _wikipedia_slug("https://ja.wikipedia.org/wiki/X") is None
    assert _wikipedia_slug("https://de.wikipedia.org/wiki/Y") is None


def test_build_item_uses_spotify_uri_as_id():
    item = _build_item(_album())
    assert item.id == "spotify:album:5eg56dCpFn32neJak2vk0f"
    assert item.kind == "album"
    assert item.title == "Crazysexycool"
    assert item.year == 1994
    assert item.creators == ["TLC"]
    assert item.metadata == {}
    spotify_uri = "spotify:album:5eg56dCpFn32neJak2vk0f"
    assert item.external_ids["spotify"] == spotify_uri
    assert item.external_ids["1001albums"] == "uuid-tlc"
    assert item.external_ids["wikipedia"] == "CrazySexyCool"
    assert item.external_ids["tidal"] == "667700"


def test_build_item_falls_back_to_1001albums_id_when_no_spotify():
    item = _build_item(_album(spotifyId=None))
    assert item.id == "1001albums:uuid-tlc"
    assert "spotify" not in item.external_ids


def test_import_creates_item_and_log(albums_store):
    result = import_project(albums_store, _project([_entry()]))
    assert len(result.items_added) == 1
    assert len(result.log_added) == 1
    items = albums_store.items("album")
    log = albums_store.log()
    assert len(items) == 1
    assert items[0].title == "Crazysexycool"
    assert len(log) == 1
    assert log[0].status == "consumed"
    assert log[0].notes == "★★★★☆"


def test_import_skips_unrevealed(albums_store):
    data = _project(
        [
            _entry(),
            _entry(revealedAlbum=False, generatedAlbumId="gen-2"),
        ],
    )
    result = import_project(albums_store, data)
    assert len(result.items_added) == 1
    assert result.skipped_unrevealed == 1


def test_import_promotes_from_want_queue(albums_store):
    # Pre-seed: the same spotify id is already on the want queue with
    # a barer record (no external_ids beyond what the user typed).
    from great.models import Item  # noqa: PLC0415

    want_id = "spotify:album:5eg56dCpFn32neJak2vk0f"
    albums_store.add_want(
        Item(id=want_id, kind="album", title="Crazysexycool"),
    )
    result = import_project(albums_store, _project([_entry()]))
    assert len(result.items_added) == 0
    assert len(result.items_promoted) == 1
    # Want queue is now empty; the catalog has the richer imported item.
    assert albums_store.wants("album") == []
    items = albums_store.items("album")
    assert len(items) == 1
    assert items[0].external_ids["1001albums"] == "uuid-tlc"


def test_import_dry_run_does_not_promote(albums_store):
    from great.models import Item  # noqa: PLC0415

    want_id = "spotify:album:5eg56dCpFn32neJak2vk0f"
    albums_store.add_want(
        Item(id=want_id, kind="album", title="Crazysexycool"),
    )
    result = import_project(
        albums_store,
        _project([_entry()]),
        dry_run=True,
    )
    assert len(result.items_promoted) == 1
    assert len(albums_store.wants("album")) == 1
    assert albums_store.items("album") == []


def test_import_refreshes_existing_item_when_source_changes(albums_store):
    # First import lands a baseline.
    import_project(albums_store, _project([_entry()]))
    # Upstream "fixes" the title, year, and adds a deezer id.
    changed = _entry(
        album=_album(name="CrazySexyCool", releaseDate="1995", deezerId=42),
    )
    result = import_project(albums_store, _project([changed]))
    assert len(result.items_refreshed) == 1
    items = albums_store.items("album")
    assert len(items) == 1
    assert items[0].title == "CrazySexyCool"
    assert items[0].year == 1995
    assert items[0].external_ids["deezer"] == "42"


def test_import_refresh_preserves_user_added_metadata_and_external_ids(
    albums_store,
):
    from great.models import Item  # noqa: PLC0415

    # User pre-seeded the album with a personal note and private id.
    base = _build_item(_album())
    seeded = Item(
        id=base.id,
        kind="album",
        title=base.title,
        year=base.year,
        creators=base.creators,
        external_ids={**base.external_ids, "bandcamp": "tlc-private"},
        metadata={"rec_by": "alex"},
    )
    albums_store.write_items("album", [seeded])
    # Re-import: upstream changes the title.
    changed = _entry(album=_album(name="CrazySexyCool"))
    import_project(albums_store, _project([changed]))
    items = albums_store.items("album")
    assert items[0].title == "CrazySexyCool"
    assert items[0].creators == ["TLC"]
    assert items[0].external_ids["bandcamp"] == "tlc-private"
    assert items[0].metadata == {"rec_by": "alex"}


def test_import_refresh_dry_run_does_not_write(albums_store):
    import_project(albums_store, _project([_entry()]))
    changed = _entry(album=_album(name="CrazySexyCool"))
    result = import_project(albums_store, _project([changed]), dry_run=True)
    assert len(result.items_refreshed) == 1
    # On disk the title is still the original.
    assert albums_store.items("album")[0].title == "Crazysexycool"


def test_import_is_idempotent(albums_store):
    data = _project([_entry()])
    import_project(albums_store, data)
    second = import_project(albums_store, data)
    assert len(second.items_added) == 0
    assert len(second.log_added) == 0
    assert second.items_existing == 1
    assert second.log_existing == 1
    assert len(albums_store.items("album")) == 1
    assert len(albums_store.log()) == 1


def test_import_dry_run_writes_nothing(albums_store):
    result = import_project(
        albums_store,
        _project([_entry()]),
        dry_run=True,
    )
    assert len(result.items_added) == 1
    assert len(result.log_added) == 1
    assert albums_store.items("album") == []
    assert albums_store.log() == []


def test_import_distinct_dates_for_same_album_log_both(albums_store):
    # The same album re-rolled on a different date is a separate diary
    # entry — log dedup keys include the timestamp.
    data = _project(
        [
            _entry(generatedAt="2025-06-26T03:01:04.115Z"),
            _entry(
                generatedAlbumId="gen-2",
                generatedAt="2026-01-10T03:01:04.115Z",
            ),
        ],
    )
    result = import_project(albums_store, data)
    assert len(result.items_added) == 1  # same album, single item
    assert len(result.log_added) == 2  # two diary entries
    assert len(albums_store.log()) == 2


def test_cli_imports_and_persists_username(tmp_path):
    Store.init(
        tmp_path,
        GreatConfig(lists=[ListConfig(name="albums", kind="album")]),
    )
    with patch(
        "great._cli.fetch_project",
        return_value=_project([_entry()]),
    ) as fetch:
        result = CliRunner().invoke(
            app,
            ["--root", str(tmp_path), "import", "1001albums", "alice"],
        )
    assert result.exit_code == 0, result.output
    fetch.assert_called_once_with("alice")
    assert "Added 1 album" in result.output
    assert "Saved username" in result.output
    # Username is now persisted; subsequent calls need no arg.
    persisted = Store(tmp_path)
    assert persisted.config.sources["albumsgenerator"]["username"] == "alice"


def test_cli_import_auto_creates_artist_items(tmp_path):
    Store.init(
        tmp_path,
        GreatConfig(
            lists=[
                ListConfig(name="albums", kind="album"),
                ListConfig(name="artists", kind="artist"),
            ],
        ),
    )
    with patch(
        "great._cli.fetch_project",
        return_value=_project([_entry()]),
    ):
        result = CliRunner().invoke(
            app,
            ["--root", str(tmp_path), "import", "1001albums", "alice"],
        )
    assert result.exit_code == 0, result.output
    # Artist creation is transparent — the user sees the album count, not
    # a separate "backfilled" line, but the artists.toml is populated.
    assert "backfill" not in result.output.lower()
    persisted = Store(tmp_path)
    assert {i.title for i in persisted.items("artist")} == {"TLC"}


def test_cli_uses_persisted_username(tmp_path):
    config = GreatConfig(
        lists=[ListConfig(name="albums", kind="album")],
        sources={"albumsgenerator": {"username": "bob"}},
    )
    Store.init(tmp_path, config)
    with patch(
        "great._cli.fetch_project",
        return_value=_project([_entry()]),
    ) as fetch:
        result = CliRunner().invoke(
            app,
            ["--root", str(tmp_path), "import", "1001albums"],
        )
    assert result.exit_code == 0, result.output
    fetch.assert_called_once_with("bob")
    assert "Saved username" not in result.output  # nothing changed


def test_cli_errors_when_no_username(tmp_path):
    Store.init(
        tmp_path,
        GreatConfig(lists=[ListConfig(name="albums", kind="album")]),
    )
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "import", "1001albums"],
    )
    assert result.exit_code != 0
    assert "No username" in result.output


def test_cli_dry_run_does_not_persist(tmp_path):
    Store.init(
        tmp_path,
        GreatConfig(lists=[ListConfig(name="albums", kind="album")]),
    )
    with patch(
        "great._cli.fetch_project",
        return_value=_project([_entry()]),
    ):
        result = CliRunner().invoke(
            app,
            [
                "--root",
                str(tmp_path),
                "import",
                "1001albums",
                "alice",
                "--dry-run",
            ],
        )
    assert result.exit_code == 0
    assert "Would add" in result.output
    persisted = Store(tmp_path)
    assert "albumsgenerator" not in persisted.config.sources
    assert persisted.items("album") == []


def _stub_items(n):
    from great.models import Item  # noqa: PLC0415

    return [Item(id=f"x{i}", kind="album", title=f"t{i}") for i in range(n)]


def _stub_logs(n):
    from datetime import UTC, datetime  # noqa: PLC0415

    from great.models import LogEntry  # noqa: PLC0415

    return [
        LogEntry(
            ts=datetime(2026, 1, i + 1, tzinfo=UTC),
            kind="album",
            item=f"x{i}",
            status="consumed",
        )
        for i in range(n)
    ]


def test_summarize_up_to_date_when_nothing_changed():
    result = ImportResult(items_existing=40, log_existing=40)
    msg = summarize(result, dry_run=False)
    assert msg.startswith("Up to date")
    assert "40 albums" in msg
    assert "40 log entries" in msg


def test_summarize_lists_only_nonzero_clauses():
    result = ImportResult(items_added=_stub_items(5), log_added=_stub_logs(5))
    msg = summarize(result, dry_run=False)
    assert msg.startswith("Added 5 albums")
    assert "refresh" not in msg
    assert "promote" not in msg


def test_summarize_appends_unrevealed_skip_count():
    result = ImportResult(
        items_added=_stub_items(1),
        log_added=_stub_logs(1),
        skipped_unrevealed=3,
    )
    msg = summarize(result, dry_run=False)
    assert msg.endswith("(3 unrevealed skipped.)")


def test_summarize_dry_run_uses_future_tense():
    result = ImportResult(items_added=_stub_items(1), log_added=_stub_logs(1))
    msg = summarize(result, dry_run=True)
    assert msg.startswith("Would add")


def test_summarize_pluralizes_singular_one():
    result = ImportResult(items_added=_stub_items(1), log_added=_stub_logs(1))
    msg = summarize(result, dry_run=False)
    assert "1 album" in msg
    assert "1 albums" not in msg
    assert "1 diary entry" in msg


def test_fetch_project_wraps_network_errors():
    import httpx  # noqa: PLC0415

    from great.albumsgenerator import (  # noqa: PLC0415
        AlbumsGeneratorError,
        fetch_project,
    )

    def boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns failure")

    with (
        httpx.Client(transport=httpx.MockTransport(boom)) as client,
        pytest.raises(AlbumsGeneratorError, match="could not reach"),
    ):
        fetch_project("alice", client=client)


def test_fetch_project_wraps_bad_json():
    import httpx  # noqa: PLC0415

    from great.albumsgenerator import (  # noqa: PLC0415
        AlbumsGeneratorError,
        fetch_project,
    )

    def not_json(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>nope</html>")

    with (
        httpx.Client(transport=httpx.MockTransport(not_json)) as client,
        pytest.raises(AlbumsGeneratorError, match="invalid JSON"),
    ):
        fetch_project("alice", client=client)


def test_fetch_project_raises_project_not_found_on_404():
    import httpx  # noqa: PLC0415

    from great.albumsgenerator import (  # noqa: PLC0415
        ProjectNotFoundError,
        fetch_project,
    )

    def not_found(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": True})

    with (
        httpx.Client(transport=httpx.MockTransport(not_found)) as client,
        pytest.raises(ProjectNotFoundError, match="ghost"),
    ):
        fetch_project("ghost", client=client)


def test_cli_surfaces_project_not_found(tmp_path):
    Store.init(
        tmp_path,
        GreatConfig(lists=[ListConfig(name="albums", kind="album")]),
    )
    with patch(
        "great._cli.fetch_project",
        side_effect=ProjectNotFoundError("no such user"),
    ):
        result = CliRunner().invoke(
            app,
            ["--root", str(tmp_path), "import", "1001albums", "ghost"],
        )
    assert result.exit_code != 0
    assert "no such user" in result.output

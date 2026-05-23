"""Tests for the 1001albums importer."""

from typing import Any
from unittest.mock import patch

from typer.testing import CliRunner
import pytest

from great._cli import app
from great.albumsgenerator import (
    ProjectNotFoundError,
    _build_item,
    _log_notes,
    _parse_year,
    _wikipedia_slug,
    import_project,
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
    assert _log_notes({"rating": 4, "review": ""}) == "4/5"
    assert _log_notes({"rating": 0, "review": "loved it"}) == "loved it"
    assert _log_notes({"rating": 5, "review": "wow"}) == "5/5 — wow"
    assert _log_notes({"rating": 0, "review": ""}) is None
    assert _log_notes({}) is None


def test_wikipedia_slug_extracts_path():
    url = "https://en.wikipedia.org/wiki/Live!_(Fela_Kuti_album)"
    assert _wikipedia_slug(url) == "Live!_(Fela_Kuti_album)"


def test_wikipedia_slug_returns_none_for_non_wiki():
    assert _wikipedia_slug("https://example.com/foo") is None


def test_build_item_uses_spotify_uri_as_id():
    item = _build_item(_album())
    assert item.id == "spotify:album:5eg56dCpFn32neJak2vk0f"
    assert item.kind == "album"
    assert item.title == "Crazysexycool"
    assert item.year == 1994
    assert item.metadata == {"artist": "TLC"}
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
    assert log[0].notes == "4/5"


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
    assert "Added 1 album(s)" in result.output
    assert "Saved username" in result.output
    # Username is now persisted; subsequent calls need no arg.
    persisted = Store(tmp_path)
    assert persisted.config.sources["albumsgenerator"]["username"] == "alice"


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

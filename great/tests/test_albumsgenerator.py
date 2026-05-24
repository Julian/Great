"""Tests for the 1001albums provider."""

from typing import Any
from unittest.mock import patch
import json

from typer.testing import CliRunner
import httpx
import pytest

from great._cli import app
from great.albumsgenerator import (
    CACHE_FILENAME,
    AlbumsGeneratorError,
    ProjectNotFoundError,
    _build_item,
    _log_notes,
    _parse_year,
    _wikipedia_slug,
    fetch_project,
    load_project,
    provider_items,
    provider_log_entries,
    save_project,
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


# -- Pure helpers ----------------------------------------------------------


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
    assert _wikipedia_slug("https://ja.wikipedia.org/wiki/X") is None
    assert _wikipedia_slug("https://de.wikipedia.org/wiki/Y") is None


def test_build_item_uses_spotify_uri_as_id():
    item = _build_item(_album())
    assert item.id == "spotify:album:5eg56dCpFn32neJak2vk0f"
    assert item.kind == "album"
    assert item.title == "Crazysexycool"
    assert item.year == 1994
    assert item.creators == ["TLC"]
    spotify_uri = "spotify:album:5eg56dCpFn32neJak2vk0f"
    assert item.external_ids["spotify"] == spotify_uri
    assert item.external_ids["1001albums"] == "uuid-tlc"
    assert item.external_ids["wikipedia"] == "CrazySexyCool"
    assert item.external_ids["tidal"] == "667700"


def test_build_item_falls_back_to_1001albums_id_when_no_spotify():
    item = _build_item(_album(spotifyId=None))
    assert item.id == "1001albums:uuid-tlc"
    assert "spotify" not in item.external_ids


# -- HTTP fetch + cache --------------------------------------------------


def test_fetch_project_raises_project_not_found_on_404():
    def not_found(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": True})

    with (
        httpx.Client(transport=httpx.MockTransport(not_found)) as client,
        pytest.raises(ProjectNotFoundError, match="ghost"),
    ):
        fetch_project("ghost", client=client)


def test_fetch_project_wraps_network_errors():
    def boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns failure")

    with (
        httpx.Client(transport=httpx.MockTransport(boom)) as client,
        pytest.raises(AlbumsGeneratorError, match="could not reach"),
    ):
        fetch_project("alice", client=client)


def test_fetch_project_wraps_bad_json():
    def not_json(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>nope</html>")

    with (
        httpx.Client(transport=httpx.MockTransport(not_json)) as client,
        pytest.raises(AlbumsGeneratorError, match="invalid JSON"),
    ):
        fetch_project("alice", client=client)


def test_save_and_load_project_roundtrip(tmp_path):
    data = _project([_entry()])
    save_project(tmp_path, data)
    assert (tmp_path / CACHE_FILENAME).is_file()
    assert load_project(tmp_path) == data


def test_load_project_returns_none_when_no_cache(tmp_path):
    assert load_project(tmp_path) is None


# -- Provider read paths -------------------------------------------------


def test_provider_items_yields_revealed_albums(tmp_path):
    save_project(
        tmp_path,
        _project(
            [
                _entry(),
                _entry(revealedAlbum=False, generatedAlbumId="gen-2"),
            ],
        ),
    )
    items = list(provider_items(tmp_path))
    assert len(items) == 1
    assert items[0].title == "Crazysexycool"


def test_provider_log_entries_synthesizes_consumed_entries(tmp_path):
    save_project(tmp_path, _project([_entry()]))
    entries = list(provider_log_entries(tmp_path))
    assert len(entries) == 1
    assert entries[0].status == "consumed"
    assert entries[0].notes == "★★★★☆"
    assert entries[0].kind == "album"


def test_provider_yields_nothing_when_no_cache(tmp_path):
    assert list(provider_items(tmp_path)) == []
    assert list(provider_log_entries(tmp_path)) == []


# -- Store integration ---------------------------------------------------


@pytest.fixture
def albums_store(tmp_path):
    config = GreatConfig(
        lists=[
            ListConfig(name="albums", kind="album"),
            ListConfig(name="artists", kind="artist"),
        ],
    )
    return Store.init(tmp_path, config)


def test_provider_items_surface_via_store_after_save(albums_store):
    save_project(albums_store.sources_dir, _project([_entry()]))
    items = albums_store.items("album")
    assert {i.title for i in items} == {"Crazysexycool"}
    # And the artist auto-creates during compile.
    artists = albums_store.items("artist")
    assert {a.title for a in artists} == {"TLC"}


def test_provider_log_entries_surface_via_store_log(albums_store):
    save_project(albums_store.sources_dir, _project([_entry()]))
    entries = albums_store.log()
    assert len(entries) == 1
    assert entries[0].kind == "album"
    assert entries[0].status == "consumed"


def test_refreshing_cache_updates_derived_view(albums_store):
    save_project(albums_store.sources_dir, _project([_entry()]))
    assert albums_store.items("album")[0].title == "Crazysexycool"
    # Source data changes upstream (title corrected) — re-saving the
    # cache and reading again should reflect it.
    save_project(
        albums_store.sources_dir,
        _project([_entry(album=_album(name="CrazySexyCool"))]),
    )
    assert albums_store.items("album")[0].title == "CrazySexyCool"


# -- CLI ------------------------------------------------------------------


def test_cli_import_saves_cache_and_persists_username(tmp_path):
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
            ["--root", str(tmp_path), "import", "1001albums", "alice"],
        )
    assert result.exit_code == 0, result.output
    assert "Imported 1 albums" in result.output
    assert "Saved username" in result.output
    cache = json.loads((tmp_path / "sources" / CACHE_FILENAME).read_text())
    assert cache["name"] == "user"
    persisted = Store(tmp_path)
    assert persisted.config.sources["albumsgenerator"]["username"] == "alice"


def test_cli_import_uses_persisted_username(tmp_path):
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
    assert "Saved username" not in result.output


def test_cli_import_errors_when_no_username(tmp_path):
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


def test_cli_import_dry_run_does_not_write_cache(tmp_path):
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
    assert result.exit_code == 0, result.output
    assert "Would import" in result.output
    assert not (tmp_path / "sources" / CACHE_FILENAME).exists()
    persisted = Store(tmp_path)
    assert "albumsgenerator" not in persisted.config.sources


def test_cli_import_surfaces_project_not_found(tmp_path):
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

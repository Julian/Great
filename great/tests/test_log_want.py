from typer.testing import CliRunner
import pytest

from great._cli import (
    AmbiguousItemError,
    ItemNotFoundError,
    NoWantListError,
    app,
    infer_want_list,
    resolve_item,
)
from great.models import GreatConfig, Item, ListConfig
from great.store import Store


@pytest.fixture
def store(tmp_path):
    config = GreatConfig(
        lists=[
            ListConfig(name="movies", kind="movie"),
            ListConfig(name="tv", kind="tv"),
        ],
    )
    store = Store.init(tmp_path, config)
    store.write_items(
        "movie",
        [
            Item(id="tt1", kind="movie", title="Anora", year=2024),
            Item(id="tt2", kind="movie", title="Casablanca", year=1942),
        ],
    )
    store.write_items(
        "tv",
        [
            Item(id="tv1", kind="tv", title="Severance", year=2022),
            Item(id="tv2", kind="tv", title="Anora", year=2024),  # same title
        ],
    )
    return store


def test_resolve_by_id(store):
    assert resolve_item(store, "tt2").title == "Casablanca"


def test_resolve_by_title_case_insensitive(store):
    assert resolve_item(store, "casablanca").id == "tt2"


def test_resolve_unique_title_across_kinds(store):
    assert resolve_item(store, "Severance").id == "tv1"


def test_resolve_by_external_id(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    store = Store.init(tmp_path, config)
    store.write_items(
        "movie",
        [
            Item(
                id="The Godfather",
                kind="movie",
                title="The Godfather",
                external_ids={"imdb": "tt0068646"},
            ),
        ],
    )
    assert resolve_item(store, "tt0068646").title == "The Godfather"


def test_resolve_unknown_raises(store):
    with pytest.raises(ItemNotFoundError):
        resolve_item(store, "Nope")


def test_resolve_ambiguous_raises(store):
    with pytest.raises(AmbiguousItemError, match="2 items"):
        resolve_item(store, "Anora")


def test_resolve_ambiguous_with_kind_disambiguates(store):
    assert resolve_item(store, "Anora", kind="movie").id == "tt1"
    assert resolve_item(store, "Anora", kind="tv").id == "tv2"


def test_infer_want_list_unique(store):
    assert infer_want_list(store, "movie") == "movies"


def test_infer_want_list_missing(store):
    with pytest.raises(NoWantListError):
        infer_want_list(store, "song")


def test_infer_want_list_ambiguous(tmp_path):
    config = GreatConfig(
        lists=[
            ListConfig(name="movies", kind="movie"),
            ListConfig(name="movies-2024", kind="movie"),
        ],
    )
    store = Store.init(tmp_path, config)
    with pytest.raises(NoWantListError):
        infer_want_list(store, "movie")


def test_log_command_records_entry(store):
    result = CliRunner().invoke(
        app,
        ["--root", str(store.root), "log", "Casablanca"],
    )
    assert result.exit_code == 0
    [entry] = store.log()
    assert entry.item == "tt2"
    assert entry.status == "consumed"


def test_log_command_with_notes_and_status(store):
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(store.root),
            "log",
            "Casablanca",
            "--status",
            "started",
            "--notes",
            "first half tonight",
        ],
    )
    assert result.exit_code == 0
    [entry] = store.log()
    assert entry.status == "started"
    assert entry.notes == "first half tonight"


def test_log_command_with_at_backdates(store):
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(store.root),
            "log",
            "Casablanca",
            "--at",
            "2025-01-15",
        ],
    )
    assert result.exit_code == 0
    [entry] = store.log(year=2025)
    assert entry.ts.year == 2025
    assert entry.ts.month == 1
    assert entry.ts.day == 15


def test_consumed_command_with_at(store):
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(store.root),
            "consumed",
            "Casablanca",
            "--at",
            "2024-12-31T20:30:00",
        ],
    )
    assert result.exit_code == 0
    [entry] = store.log(year=2024)
    assert entry.ts.year == 2024
    assert entry.status == "consumed"


def test_log_command_unknown_item_fails(store):
    result = CliRunner().invoke(
        app,
        ["--root", str(store.root), "log", "NotAThing"],
    )
    assert result.exit_code == 1


def test_log_command_ambiguous_fails(store):
    result = CliRunner().invoke(
        app,
        ["--root", str(store.root), "log", "Anora"],
    )
    assert result.exit_code == 1
    assert "matches 2 items" in result.output.lower() or "matches 2 items" in (
        result.stderr or ""
    )


def test_log_command_kind_disambiguates(store):
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(store.root),
            "log",
            "Anora",
            "--kind",
            "movie",
        ],
    )
    assert result.exit_code == 0
    [entry] = store.log()
    assert entry.item == "tt1"


def test_consumed_command(store):
    result = CliRunner().invoke(
        app,
        ["--root", str(store.root), "consumed", "Casablanca"],
    )
    assert result.exit_code == 0
    [entry] = store.log()
    assert entry.status == "consumed"


def test_want_command_infers_list(store):
    result = CliRunner().invoke(
        app,
        ["--root", str(store.root), "want", "Casablanca"],
    )
    assert result.exit_code == 0
    [w] = store.wants("movies")
    assert w.item == "tt2"
    assert w.priority == "normal"


def test_want_command_explicit_list_and_priority(store):
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(store.root),
            "want",
            "Severance",
            "--list",
            "tv",
            "--priority",
            "high",
        ],
    )
    assert result.exit_code == 0
    [w] = store.wants("tv")
    assert w.priority == "high"


def test_log_prunes_item_from_want_list(store):
    CliRunner().invoke(
        app,
        ["--root", str(store.root), "want", "Casablanca"],
    )
    assert len(store.wants("movies")) == 1

    result = CliRunner().invoke(
        app,
        ["--root", str(store.root), "consumed", "Casablanca"],
    )
    assert result.exit_code == 0
    assert "removed from 1 want list" in result.output.lower()
    assert store.wants("movies") == []


def test_log_prunes_across_multiple_want_lists(tmp_path):
    config = GreatConfig(
        lists=[
            ListConfig(name="movies", kind="movie"),
            ListConfig(name="favorites", kind="movie"),
        ],
    )
    store = Store.init(tmp_path, config)
    store.write_items(
        "movie",
        [Item(id="tt1", kind="movie", title="Anora")],
    )
    CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "want", "Anora", "--list", "movies"],
    )
    CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "want", "Anora", "--list", "favorites"],
    )
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "consumed", "Anora", "--kind", "movie"],
    )
    assert result.exit_code == 0
    assert "removed from 2 want lists" in result.output.lower()
    assert store.wants("movies") == []
    assert store.wants("favorites") == []


def test_log_does_not_remove_other_items(store):
    CliRunner().invoke(
        app,
        ["--root", str(store.root), "want", "Anora", "--kind", "movie"],
    )
    CliRunner().invoke(
        app,
        ["--root", str(store.root), "want", "Casablanca"],
    )
    CliRunner().invoke(
        app,
        ["--root", str(store.root), "consumed", "Anora", "--kind", "movie"],
    )
    [remaining] = store.wants("movies")
    assert remaining.item == "tt2"


def test_unwant_removes_from_all_when_no_list(store):
    CliRunner().invoke(
        app,
        ["--root", str(store.root), "want", "Casablanca"],
    )
    result = CliRunner().invoke(
        app,
        ["--root", str(store.root), "unwant", "Casablanca"],
    )
    assert result.exit_code == 0
    assert store.wants("movies") == []


def test_unwant_no_op_for_unwanted_item(store):
    result = CliRunner().invoke(
        app,
        ["--root", str(store.root), "unwant", "Casablanca"],
    )
    assert result.exit_code == 0
    assert "not on any want list" in result.output.lower()


def test_unwant_specific_list(tmp_path):
    config = GreatConfig(
        lists=[
            ListConfig(name="movies", kind="movie"),
            ListConfig(name="favorites", kind="movie"),
        ],
    )
    store = Store.init(tmp_path, config)
    store.write_items(
        "movie",
        [Item(id="tt1", kind="movie", title="Anora")],
    )
    CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "want", "Anora", "--list", "movies"],
    )
    CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "want", "Anora", "--list", "favorites"],
    )
    CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "unwant", "Anora", "--list", "movies"],
    )
    assert store.wants("movies") == []
    assert len(store.wants("favorites")) == 1


def test_want_command_ambiguous_list_requires_flag(tmp_path):
    config = GreatConfig(
        lists=[
            ListConfig(name="movies", kind="movie"),
            ListConfig(name="movies-2024", kind="movie"),
        ],
    )
    store = Store.init(tmp_path, config)
    store.write_items(
        "movie",
        [Item(id="tt1", kind="movie", title="Anora")],
    )
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "want", "Anora"],
    )
    assert result.exit_code == 1

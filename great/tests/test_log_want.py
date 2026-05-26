from typer.testing import CliRunner
import pytest

from great._cli import app
from great.lookup import AmbiguousItemError, ItemNotFoundError, resolve_item
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


def test_resolve_can_include_wants(store):
    pick = Item(id="Watchlist Pick", kind="movie", title="Watchlist Pick")
    store.add_want(pick)
    assert resolve_item(store, "Watchlist Pick", search_wants=True).id == (
        "Watchlist Pick"
    )
    with pytest.raises(ItemNotFoundError):
        resolve_item(store, "Watchlist Pick")


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


def test_want_command_adds_free_title(store):
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(store.root),
            "want",
            "Brand New Cherry Flavor",
            "--kind",
            "tv",
        ],
    )
    assert result.exit_code == 0, result.output
    [w] = store.wants("tv")
    assert w.title == "Brand New Cherry Flavor"
    assert w.kind == "tv"
    assert w.id == "Brand New Cherry Flavor"


def test_want_command_with_year_and_id(store):
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(store.root),
            "want",
            "Casablanca II",
            "--kind",
            "movie",
            "--year",
            "2030",
            "--id",
            "tt-cas2",
        ],
    )
    assert result.exit_code == 0, result.output
    [w] = store.wants("movie")
    assert w.id == "tt-cas2"
    assert w.year == 2030


def test_want_command_requires_kind(store):
    result = CliRunner().invoke(
        app,
        ["--root", str(store.root), "want", "Some Title"],
    )
    assert result.exit_code != 0


def test_want_command_rejects_already_consumed(store):
    # Re-add the same id that already exists in items/movies.toml (tt2).
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(store.root),
            "want",
            "Casablanca II",
            "--kind",
            "movie",
            "--id",
            "tt2",
        ],
    )
    assert result.exit_code == 1
    err = (result.output + (result.stderr or "")).lower()
    assert "already in items" in err
    assert store.wants("movie") == []


def test_consumed_promotes_want_to_catalog(store):
    CliRunner().invoke(
        app,
        [
            "--root",
            str(store.root),
            "want",
            "Brand New Cherry Flavor",
            "--kind",
            "tv",
        ],
    )
    assert len(store.wants("tv")) == 1

    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(store.root),
            "consumed",
            "Brand New Cherry Flavor",
            "--no-rank",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "promoted from want queue" in result.output.lower()
    assert store.wants("tv") == []
    titles = {i.title for i in store.items("tv")}
    assert "Brand New Cherry Flavor" in titles


def test_log_never_promotes_from_want_queue(store):
    """``log`` is a pure diary appender — promotion is ``consumed``'s job."""
    CliRunner().invoke(
        app,
        [
            "--root",
            str(store.root),
            "want",
            "Brand New Cherry Flavor",
            "--kind",
            "tv",
        ],
    )
    for status in ("consumed", "started", "abandoned"):
        result = CliRunner().invoke(
            app,
            [
                "--root",
                str(store.root),
                "log",
                "Brand New Cherry Flavor",
                "--status",
                status,
            ],
        )
        assert result.exit_code == 0, result.output
        assert "promoted" not in result.output.lower()
    assert len(store.wants("tv")) == 1


def test_unwant_removes_from_kind(store):
    CliRunner().invoke(
        app,
        [
            "--root",
            str(store.root),
            "want",
            "Brand New Cherry Flavor",
            "--kind",
            "tv",
        ],
    )
    result = CliRunner().invoke(
        app,
        ["--root", str(store.root), "unwant", "Brand New Cherry Flavor"],
    )
    assert result.exit_code == 0, result.output
    assert store.wants("tv") == []


def test_unwant_no_op_for_unwanted_item(store):
    result = CliRunner().invoke(
        app,
        ["--root", str(store.root), "unwant", "Casablanca"],
    )
    assert result.exit_code == 0
    assert "not on any want queue" in result.output.lower()


def test_unwant_ambiguous_across_kinds_requires_kind(store):
    CliRunner().invoke(
        app,
        ["--root", str(store.root), "want", "Dual", "--kind", "movie"],
    )
    CliRunner().invoke(
        app,
        ["--root", str(store.root), "want", "Dual", "--kind", "tv"],
    )
    result = CliRunner().invoke(
        app,
        ["--root", str(store.root), "unwant", "Dual"],
    )
    assert result.exit_code == 1
    assert "matches 2 items" in result.output.lower() or (
        "matches 2 items" in (result.stderr or "")
    )

    result_ok = CliRunner().invoke(
        app,
        ["--root", str(store.root), "unwant", "Dual", "--kind", "movie"],
    )
    assert result_ok.exit_code == 0
    assert store.wants("movie") == []
    assert len(store.wants("tv")) == 1

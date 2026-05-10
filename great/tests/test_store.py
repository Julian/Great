from datetime import UTC, date, datetime

import pytest

from great.models import (
    Comparison,
    GreatConfig,
    Item,
    ListConfig,
    LogEntry,
    WantEntry,
)
from great.store import (
    ListNotFoundError,
    Store,
    StoreNotFoundError,
)


@pytest.fixture
def store(tmp_path):
    config = GreatConfig(
        lists=[
            ListConfig(name="movies", kind="movie"),
            ListConfig(name="tv", kind="tv"),
        ],
    )
    return Store.init(tmp_path, config)


def test_init_creates_layout(tmp_path):
    Store.init(tmp_path, GreatConfig())
    assert (tmp_path / "great.toml").is_file()
    for sub in ("items", "comparisons", "log", "want"):
        assert (tmp_path / sub).is_dir()


def test_init_round_trips_config(tmp_path):
    config = GreatConfig(
        lists=[
            ListConfig(name="movies", kind="movie", description="all-time"),
        ],
        theme="solarized",
    )
    Store.init(tmp_path, config)
    reloaded = Store(tmp_path).config
    assert reloaded == config


def test_find_walks_up(tmp_path):
    Store.init(tmp_path, GreatConfig())
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    found = Store.find(nested)
    assert found.root == tmp_path


def test_find_raises_when_missing(tmp_path):
    with pytest.raises(StoreNotFoundError):
        Store.find(tmp_path)


def test_list_config_resolves(store):
    assert store.list_config("movies").kind == "movie"


def test_list_config_unknown(store):
    with pytest.raises(ListNotFoundError):
        store.list_config("books")


def test_items_round_trip(store):
    items = [
        Item(id="tt1", kind="movie", title="Anora", year=2024),
        Item(
            id="tt2",
            kind="movie",
            title="Conclave",
            year=2024,
            external_ids={"imdb": "tt2"},
            metadata={"director": "Edward Berger"},
        ),
    ]
    store.write_items("movie", items)
    assert store.items("movie") == items


def test_items_missing_returns_empty(store):
    assert store.items("movie") == []


def test_comparisons_append_and_read(store):
    c1 = Comparison(
        ts=datetime(2026, 5, 9, 14, 0, tzinfo=UTC),
        list="movies",
        items=["tt1", "tt2"],
        ordering=[[0], [1]],
    )
    c2 = Comparison(
        ts=datetime(2026, 5, 9, 14, 5, tzinfo=UTC),
        list="movies",
        items=["tt1", "tt3"],
        ordering=[[0, 1]],
    )
    store.append_comparison(c1)
    store.append_comparison(c2)
    assert store.comparisons("movies") == [c1, c2]


def test_comparisons_missing_returns_empty(store):
    assert store.comparisons("movies") == []


def test_log_split_by_year(store):
    a = LogEntry(
        ts=datetime(2025, 12, 31, tzinfo=UTC),
        item="tt1",
        status="consumed",
    )
    b = LogEntry(
        ts=datetime(2026, 1, 1, tzinfo=UTC),
        item="tt2",
        status="started",
        notes="paused at the diner scene",
    )
    store.append_log(a)
    store.append_log(b)
    assert store.log() == [a, b]
    assert store.log(year=2025) == [a]
    assert store.log(year=2026) == [b]


def test_wants_round_trip(store):
    w1 = WantEntry(item="tt1", added=date(2026, 5, 9))
    w2 = WantEntry(item="tt2", added=date(2026, 5, 10), priority="high")
    store.add_want("movies", w1)
    store.add_want("movies", w2)
    assert store.wants("movies") == [w1, w2]


def test_wants_missing_returns_empty(store):
    assert store.wants("movies") == []


def test_items_rejects_kind_in_file(store):
    bad = store.root / "items" / "movie.toml"
    bad.write_text(
        '[[items]]\nid = "tt1"\nkind = "movie"\ntitle = "Redundant"\n',
    )
    with pytest.raises(Exception, match="kind"):
        store.items("movie")


def test_items_rejects_duplicate_id(store):
    bad = store.root / "items" / "movie.toml"
    bad.write_text(
        '[[items]]\nid = "tt1"\ntitle = "First"\n'
        '[[items]]\nid = "tt1"\ntitle = "Second"\n',
    )
    with pytest.raises(Exception, match="duplicate"):
        store.items("movie")


def test_all_items_aggregates_across_kinds(store):
    store.write_items(
        "movie",
        [Item(id="tt1", kind="movie", title="Anora")],
    )
    store.write_items(
        "tv",
        [Item(id="tv1", kind="tv", title="Severance")],
    )
    ids = {item.id for item in store.all_items()}
    assert ids == {"tt1", "tv1"}


def test_all_items_rejects_cross_kind_id_collision(store):
    store.write_items(
        "movie",
        [Item(id="dup", kind="movie", title="Movie")],
    )
    store.write_items(
        "tv",
        [Item(id="dup", kind="tv", title="Show")],
    )
    with pytest.raises(Exception, match="globally unique"):
        store.all_items()

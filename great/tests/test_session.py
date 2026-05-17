import pytest

from great.models import GreatConfig, Item, ListConfig
from great.session import (
    InsufficientItemsError,
    RankingScope,
    add_items,
    run_rank_loop,
)
from great.store import Store


def test_run_rank_loop_records_comparison(tmp_path, make_movies_store):
    store = make_movies_store(tmp_path)

    appended = run_rank_loop(
        RankingScope.for_list(store, "movies"),
        session=lambda _cluster: [[0], [1]],
        max_iters=1,
    )

    assert appended == 1
    [c] = store.comparisons("movies")
    assert c.ordering == [[0], [1]]


def test_run_rank_loop_session_can_signal_quit(tmp_path, make_movies_store):
    store = make_movies_store(tmp_path)

    appended = run_rank_loop(
        RankingScope.for_list(store, "movies"),
        session=lambda _cluster: None,
        max_iters=10,
    )

    assert appended == 0
    assert store.comparisons("movies") == []


def test_run_rank_loop_records_tie(tmp_path, make_movies_store):
    store = make_movies_store(tmp_path)

    run_rank_loop(
        RankingScope.for_list(store, "movies"),
        session=lambda cluster: [list(range(len(cluster)))],
        max_iters=1,
    )

    [c] = store.comparisons("movies")
    assert c.ordering == [[0, 1]]


def test_run_rank_loop_orders_cluster_by_descending_mean(
    tmp_path,
    make_movies_store,
):
    items = [
        Item(id="tt1", kind="movie", title="Anora", year=2024),
        Item(id="tt2", kind="movie", title="Casablanca", year=1942),
    ]
    store = make_movies_store(tmp_path, items=items)

    seen: list[list[str]] = []

    def session(cluster):
        seen.append([item.id for item in cluster])
        if len(seen) == 1:
            return [[1], [0]]
        return None

    run_rank_loop(
        RankingScope.for_list(store, "movies"),
        session=session,
        max_iters=5,
    )

    assert len(seen) == 2
    assert seen[1][0] == "tt2"


def test_run_rank_loop_stops_when_ranking_is_settled(
    tmp_path,
    make_movies_store,
):
    items = [
        Item(id=f"tt{i}", kind="movie", title=f"M{i}", year=2000 + i)
        for i in range(6)
    ]
    store = make_movies_store(tmp_path, items=items)

    appended = run_rank_loop(
        RankingScope.for_list(store, "movies"),
        session=lambda cluster: [[i] for i in range(len(cluster))],
        max_iters=1000,
    )

    assert 0 < appended < 100


def test_run_rank_loop_focus_mode_keeps_focus_in_every_cluster(
    tmp_path,
    make_movies_store,
):
    items = [
        Item(id=f"tt{i}", kind="movie", title=f"M{i}", year=2000 + i)
        for i in range(6)
    ]
    store = make_movies_store(tmp_path, items=items)

    seen: list[list[str]] = []

    def session(cluster):
        seen.append([item.id for item in cluster])
        return [[i] for i in range(len(cluster))]

    appended = run_rank_loop(
        RankingScope.for_list(store, "movies"),
        session=session,
        max_iters=1000,
        focus_ids=["tt0"],
    )

    assert 0 < appended < 1000
    assert seen
    for cluster in seen:
        assert "tt0" in cluster


def test_run_rank_loop_focus_mode_stops_when_focus_is_settled(
    tmp_path,
    make_movies_store,
):
    items = [
        Item(id=f"tt{i}", kind="movie", title=f"M{i}", year=2000 + i)
        for i in range(6)
    ]
    store = make_movies_store(tmp_path, items=items)
    appended_focus = run_rank_loop(
        RankingScope.for_list(store, "movies"),
        session=lambda cluster: [[i] for i in range(len(cluster))],
        max_iters=1000,
        focus_ids=["tt0"],
    )
    store_unfocused = make_movies_store(tmp_path / "other", items=items)
    appended_full = run_rank_loop(
        RankingScope.for_list(store_unfocused, "movies"),
        session=lambda cluster: [[i] for i in range(len(cluster))],
        max_iters=1000,
    )
    # Focus mode settles strictly sooner: it only needs to separate
    # one item from the rest, not totally order the list.
    assert appended_focus < appended_full


def test_run_rank_loop_want_scope_writes_to_want_comparisons(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    store = Store.init(tmp_path, config)
    store.add_want(Item(id="w1", kind="movie", title="Wanted A"))
    store.add_want(Item(id="w2", kind="movie", title="Wanted B"))

    appended = run_rank_loop(
        RankingScope.for_want(store, "movie"),
        session=lambda _cluster: [[0], [1]],
        max_iters=1,
    )

    assert appended == 1
    assert store.comparisons("movies") == []
    [c] = store.want_comparisons("movie")
    assert c.ordering == [[0], [1]]


def test_run_rank_loop_refuses_too_few_items(tmp_path, make_movies_store):
    make_movies_store(
        tmp_path,
        items=[Item(id="tt1", kind="movie", title="Anora")],
    )
    store = Store.find(tmp_path)

    with pytest.raises(InsufficientItemsError):
        run_rank_loop(
            RankingScope.for_list(store, "movies"),
            session=lambda _cluster: None,
            max_iters=1,
        )


def test_add_items_runs_focused_session(tmp_path, make_movies_store):
    make_movies_store(tmp_path)
    store = Store.find(tmp_path)

    seen: list[list[str]] = []

    def session(cluster):
        seen.append([item.id for item in cluster])
        return [[i] for i in range(len(cluster))]

    result = add_items(
        store,
        "movies",
        ["Goodfellas"],
        session=session,
        max_iters=100,
    )

    assert result.appended > 0
    assert not result.skipped_ranking
    assert [(o.item.title, o.new) for o in result.outcomes] == [
        ("Goodfellas", True),
    ]
    titles = {i.title for i in store.items("movie")}
    assert titles == {"Anora", "Casablanca", "Goodfellas"}
    assert seen
    for cluster in seen:
        assert "Goodfellas" in cluster


def test_add_items_skips_ranking_when_below_min_k(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    store = Store.init(tmp_path, config)

    def session(_cluster):
        raise AssertionError("session should not run below MIN_K")

    result = add_items(
        store,
        "movies",
        ["The Godfather"],
        session=session,
    )

    assert result.appended == 0
    assert result.skipped_ranking
    [outcome] = result.outcomes
    assert outcome.new
    assert outcome.item.title == "The Godfather"


def test_add_items_skips_ranking_when_all_duplicates(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    store = Store.init(tmp_path, config)
    store.write_items(
        "movie",
        [
            Item(id="Anora", kind="movie", title="Anora"),
            Item(id="Casablanca", kind="movie", title="Casablanca"),
        ],
    )

    def session(_cluster):
        raise AssertionError("session should not run when nothing was added")

    result = add_items(
        store,
        "movies",
        ["Anora", "Casablanca"],
        session=session,
    )

    assert result.appended == 0
    assert not result.skipped_ranking
    assert all(not o.new for o in result.outcomes)

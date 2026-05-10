from datetime import UTC, datetime
import random

import pytest

from great.models import Comparison, Item
from great.ranking import (
    COLD_START_VARIANCE,
    Score,
    infer,
    rescale_to_quantiles,
    select_cluster,
)


def _movie(id_: str, title: str | None = None) -> Item:
    return Item(id=id_, kind="movie", title=title or id_)


def _comp(items_: list[str], ordering, when: int = 1) -> Comparison:
    return Comparison(
        ts=datetime(2026, 5, when, tzinfo=UTC),
        list="movies",
        items=items_,
        ordering=ordering,
    )


def test_infer_empty():
    assert infer([], []) == {}


def test_infer_no_comparisons_returns_prior():
    items = [_movie("a"), _movie("b")]
    scores = infer([], items)
    assert scores == {
        "a": Score(0.0, COLD_START_VARIANCE),
        "b": Score(0.0, COLD_START_VARIANCE),
    }


def test_infer_pairwise_winner_has_higher_mean():
    items = [_movie("a"), _movie("b")]
    comparisons = [_comp(["a", "b"], [[0], [1]])] * 5
    scores = infer(comparisons, items)
    assert scores["a"].mean > scores["b"].mean


def test_infer_kway_preserves_order():
    items = [_movie("a"), _movie("b"), _movie("c")]
    comparisons = [_comp(["a", "b", "c"], [[0], [1], [2]])] * 5
    scores = infer(comparisons, items)
    assert scores["a"].mean > scores["b"].mean > scores["c"].mean


def test_infer_tie_gives_equal_scores():
    items = [_movie("a"), _movie("b")]
    comparisons = [_comp(["a", "b"], [[0, 1]])] * 5
    scores = infer(comparisons, items)
    assert scores["a"].mean == pytest.approx(scores["b"].mean, abs=1e-6)


def test_infer_partial_tie():
    items = [_movie("a"), _movie("b"), _movie("c")]
    comparisons = [_comp(["a", "b", "c"], [[0], [1, 2]])] * 5
    scores = infer(comparisons, items)
    assert scores["a"].mean > scores["b"].mean
    assert scores["a"].mean > scores["c"].mean
    assert scores["b"].mean == pytest.approx(scores["c"].mean, abs=1e-6)


def test_infer_drops_stale_item_ids():
    items = [_movie("a"), _movie("b")]
    comparisons = [
        _comp(["a", "ghost"], [[0], [1]]),
        _comp(["a", "b"], [[0], [1]]),
    ]
    scores = infer(comparisons, items)
    assert scores["a"].mean > scores["b"].mean
    assert "ghost" not in scores


def test_select_cluster_cold_start_returns_all():
    items = [_movie(c) for c in "abcde"]
    scores = {i.id: Score(0.0, COLD_START_VARIANCE) for i in items}
    cluster = select_cluster(scores, items, max_k=5)
    assert sorted(cluster) == sorted(["a", "b", "c", "d", "e"])


def test_select_cluster_caps_at_max_k():
    items = [_movie(c) for c in "abcdefghij"]
    scores = {i.id: Score(0.0, COLD_START_VARIANCE) for i in items}
    cluster = select_cluster(scores, items, max_k=3)
    assert len(cluster) == 3


def test_select_cluster_seeds_on_highest_variance():
    items = [_movie(c) for c in "abcdefg"]
    scores = {i.id: Score(0.0, 0.1) for i in items}
    scores["d"] = Score(0.0, 5.0)
    cluster = select_cluster(scores, items, max_k=2)
    assert "d" in cluster


def test_select_cluster_well_separated_returns_singleton():
    items = [_movie(c) for c in "abcdefghij"]
    scores = {
        i.id: Score(float(ord(i.id) - ord("a")) * 10.0, 0.01) for i in items
    }
    cluster = select_cluster(scores, items, max_k=5)
    assert len(cluster) == 1


def test_select_cluster_high_variance_seed_admits_neighbors():
    items = [_movie(c) for c in "abcdef"]
    scores = {i.id: Score(float(ord(i.id) - ord("a")), 1e-9) for i in items}
    scores["c"] = Score(2.0, 5.0)
    cluster = select_cluster(scores, items, max_k=3)
    assert "c" in cluster
    assert len(cluster) >= 2


def test_select_cluster_small_well_separated_returns_singleton():
    items = [_movie(c) for c in "abcde"]
    scores = {
        i.id: Score(float(ord(i.id) - ord("a")) * 10.0, 0.01) for i in items
    }
    cluster = select_cluster(scores, items, max_k=5)
    assert len(cluster) == 1


def test_select_cluster_small_mutually_confusable_returns_all():
    items = [_movie(c) for c in "abcde"]
    scores = {i.id: Score(0.0, 1.0) for i in items}
    cluster = select_cluster(scores, items, max_k=5)
    assert sorted(cluster) == sorted(["a", "b", "c", "d", "e"])


def test_select_cluster_force_random_seed_stays_in_top_uncertain():
    items = [_movie(c) for c in "abcdefghij"]
    scores = {i.id: Score(float(ord(i.id)), 0.1) for i in items}
    scores["a"] = Score(0.0, 100.0)
    scores["b"] = Score(98.0, 50.0)
    scores["c"] = Score(99.0, 25.0)

    top = {"a", "b", "c"}
    rng = random.Random(42)
    for _ in range(20):
        cluster = select_cluster(
            scores,
            items,
            max_k=3,
            rng=rng,
            force_random_seed=True,
        )
        assert cluster[0] in top


def test_select_cluster_orders_by_descending_confusability():
    items = [_movie(c) for c in "abcde"] + [_movie("seed")]
    scores = {
        "seed": Score(0.0, 1.0),
        "a": Score(0.1, 0.01),
        "b": Score(0.5, 0.01),
        "c": Score(1.5, 0.01),
        "d": Score(3.0, 0.01),
        "e": Score(5.0, 0.01),
    }
    cluster = select_cluster(scores, items, max_k=3)
    assert cluster[0] == "seed"
    assert cluster[1] == "a"
    assert cluster[2] == "b"


def test_select_cluster_max_k_too_small():
    with pytest.raises(ValueError, match="at least"):
        select_cluster({}, [], max_k=1)


def test_select_cluster_empty_items():
    assert select_cluster({}, [], max_k=3) == []


def test_select_cluster_force_random_seed_differs():
    items = [_movie(c) for c in "abcdefghij"]
    scores = {i.id: Score(float(ord(i.id)), 0.1) for i in items}
    scores["a"] = Score(0.0, 100.0)

    greedy = select_cluster(scores, items, max_k=2)
    rng = random.Random(0)
    random_seed = select_cluster(
        scores,
        items,
        max_k=2,
        rng=rng,
        force_random_seed=True,
    )
    assert greedy[0] == "a"
    assert random_seed != greedy or random_seed[0] != "a"


def test_rescale_empty():
    assert rescale_to_quantiles({}) == {}


def test_rescale_buckets_evenly():
    scores = {chr(ord("a") + i): Score(float(i), 0.1) for i in range(10)}
    quantiles = rescale_to_quantiles(scores, n_quantiles=5)
    assert quantiles["a"] == 0
    assert quantiles["j"] == 4
    assert sorted(quantiles.values()) == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]


def test_rescale_pair_reaches_both_extremes():
    scores = {"low": Score(0.0, 0.1), "high": Score(1.0, 0.1)}
    quantiles = rescale_to_quantiles(scores, n_quantiles=5)
    assert quantiles["low"] == 0
    assert quantiles["high"] == 4


def test_rescale_single_item_top_tier():
    quantiles = rescale_to_quantiles({"only": Score(0.0, 0.1)}, n_quantiles=5)
    assert quantiles["only"] == 4


def test_rescale_monotonic_in_score():
    scores = {chr(ord("a") + i): Score(float(i), 0.1) for i in range(7)}
    quantiles = rescale_to_quantiles(scores, n_quantiles=5)
    ordered = [quantiles[chr(ord("a") + i)] for i in range(7)]
    assert ordered == sorted(ordered)
    assert ordered[0] == 0
    assert ordered[-1] == 4

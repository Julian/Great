"""
Plackett-Luce inference, active cluster selection, quantile rescaling.

The ranking engine turns a list of :class:`Comparison` records into a
posterior distribution over Bradley-Terry / Plackett-Luce strengths,
and decides which items the user should be asked about next.
"""

from typing import NamedTuple
import math
import random

import choix
import numpy as np

from great.models import Comparison, Item

PRIOR_ALPHA = 1.0
COLD_START_VARIANCE = 1.0 / PRIOR_ALPHA
MIN_K = 2
MIN_CONFUSABILITY = 0.15


class Score(NamedTuple):
    """A posterior summary for a single item."""

    mean: float
    variance: float


def infer(
    comparisons: list[Comparison],
    items: list[Item],
) -> dict[str, Score]:
    """
    Run EP on the comparison data, returning per-item posteriors.

    Items with no informative data fall back to a high-variance prior.
    Comparisons referencing items outside ``items`` are silently
    dropped (they can be left over from items the user has removed).

    EP is run only over the items that actually participate in some
    pair. Isolated nodes (no comparisons referencing them) get the
    prior directly — under EP, a node with no incident messages
    converges to the prior, so this is equivalent to including them
    in the full ``n``-item solve. The shortcut matters at scale: a
    dense ``ep_pairwise`` builds an ``n``-by-``n`` covariance, so a
    list with thousands of items and a handful of comparisons would
    otherwise spend most of its time on items with no signal yet.
    """
    if not items:
        return {}
    item_ids = [item.id for item in items]
    id_set = set(item_ids)

    raw_pairs: list[tuple[str, str]] = []
    for c in comparisons:
        for winner, loser in _to_pairs(c):
            if winner in id_set and loser in id_set:
                raw_pairs.append((winner, loser))

    scores: dict[str, Score] = {
        iid: Score(0.0, COLD_START_VARIANCE) for iid in item_ids
    }
    if not raw_pairs:
        return scores

    participating = {iid for pair in raw_pairs for iid in pair}
    sub_ids = sorted(participating)
    sub_idx = {iid: i for i, iid in enumerate(sub_ids)}
    pairs = [(sub_idx[w], sub_idx[loser]) for w, loser in raw_pairs]

    mean, cov = choix.ep_pairwise(len(sub_ids), pairs, alpha=PRIOR_ALPHA)
    variances = np.diag(cov)
    for i, iid in enumerate(sub_ids):
        scores[iid] = Score(float(mean[i]), float(variances[i]))
    return scores


def select_cluster(
    scores: dict[str, Score],
    items: list[Item],
    max_k: int = 5,
    rng: random.Random | None = None,
    force_random_seed: bool = False,
    seed_pool: list[str] | None = None,
) -> list[str]:
    """
    Pick a cluster of items to compare next, size up to ``max_k``.

    Seeds on the highest-variance item and admits other items whose
    posterior is confusable with the seed's -- ``confusability`` being
    ``min(p, 1-p)`` where ``p = P(s_seed > s_cand)`` under the normal
    posterior approximation. Candidates are visited in order of
    descending confusability, so the cluster captures the items most
    likely to swap places with the seed.

    May return a singleton ``[seed]`` when no other item meets
    :data:`MIN_CONFUSABILITY` -- the seed is well-separated from
    everything and ranking is effectively settled. Callers should
    treat that as a signal to stop asking.

    Ties (in either variance or confusability) are broken uniformly
    at random via ``rng``, so cold-start clusters -- where every item
    shares the prior -- look like genuine random samples instead of
    whatever the input list ordering happens to be.

    ``force_random_seed`` replaces the variance-greedy seed with a
    uniform pick *among the ``max_k`` most-uncertain items*, to escape
    fixed points without spuriously seeding on a well-separated item
    (which would always collapse to a singleton). The caller is
    expected to engage this every few rounds.

    ``seed_pool`` restricts the seed to a subset of item ids (cluster
    expansion still draws from the full ``items`` list). Used to focus
    a ranking session on placing specific newly-added items: as soon
    as every focus item is well-separated from the rest, the seed --
    drawn from the focus set -- collapses to a singleton and the
    caller can stop. Returns ``[]`` if the pool is empty or its ids
    don't intersect ``items``.
    """
    if max_k < MIN_K:
        raise ValueError(f"max_k must be at least {MIN_K}")
    if not items:
        return []

    if seed_pool is not None:
        pool_ids = set(seed_pool)
        seed_candidates = [i for i in items if i.id in pool_ids]
        if not seed_candidates:
            return []
    else:
        seed_candidates = items

    rng = rng or random.Random()  # noqa: S311 (not security-sensitive)
    if force_random_seed:
        top_uncertain = sorted(
            seed_candidates,
            key=lambda i: (scores[i.id].variance, rng.random()),
            reverse=True,
        )[:max_k]
        seed = rng.choice(top_uncertain)
    else:
        seed = max(
            seed_candidates,
            key=lambda i: (scores[i.id].variance, rng.random()),
        )
    seed_score = scores[seed.id]

    scored_candidates = [
        (_confusability(seed_score, scores[i.id]), rng.random(), i.id)
        for i in items
        if i.id != seed.id
    ]
    scored_candidates.sort(reverse=True)

    cluster = [seed.id]
    for conf, _, cand_id in scored_candidates:
        if len(cluster) >= max_k or conf < MIN_CONFUSABILITY:
            break
        cluster.append(cand_id)
    return cluster


def _confusability(a: Score, b: Score) -> float:
    """
    Posterior probability the apparently-worse item is actually better.

    Computes ``min(P(s_a > s_b), P(s_b > s_a))`` under a
    normal-difference approximation. 0.5 = totally uncertain; 0 =
    well-separated.
    """
    diff_var = a.variance + b.variance
    if diff_var <= 0.0:
        return 0.5 if a.mean == b.mean else 0.0
    z = abs(a.mean - b.mean) / math.sqrt(diff_var)
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def rescale_to_quantiles(
    scores: dict[str, Score],
    n_quantiles: int = 5,
) -> dict[str, int]:
    """
    Bucket scores into ``n_quantiles`` groups, lowest = 0.

    Spreads ranks linearly across the available bucket range so that
    the lowest-ranked item is always in bucket 0 and the highest in
    ``n_quantiles - 1``, even when there are fewer items than
    quantiles. Items sharing a mean share a bucket, assigned from the
    midpoint of their run so an all-tied list lands in the middle.
    Buckets remain monotonic in score.
    """
    if not scores:
        return {}
    sorted_ids = sorted(scores.keys(), key=lambda iid: scores[iid].mean)
    n = len(sorted_ids)
    if n == 1:
        return {sorted_ids[0]: n_quantiles - 1}
    buckets: dict[str, int] = {}
    i = 0
    while i < n:
        mean = scores[sorted_ids[i]].mean
        j = i
        while j < n and scores[sorted_ids[j]].mean == mean:
            j += 1
        midpoint = (i + j - 1) / 2
        bucket = min(n_quantiles - 1, int(midpoint / (n - 1) * n_quantiles))
        for k in range(i, j):
            buckets[sorted_ids[k]] = bucket
        i = j
    return buckets


def _to_pairs(c: Comparison) -> list[tuple[str, str]]:
    """
    Decompose a comparison into (winner, loser) item-id pairs.

    Cross-group pairs convey strict preference; within-group pairs are
    emitted in both directions to encode ties symmetrically.
    """
    pairs: list[tuple[str, str]] = []
    for gi, winners in enumerate(c.ordering):
        for losers in c.ordering[gi + 1 :]:
            pairs.extend(
                (c.items[w], c.items[l_]) for w in winners for l_ in losers
            )
    for group in c.ordering:
        for i, a in enumerate(group):
            pairs.extend(
                pair
                for b in group[i + 1 :]
                for pair in (
                    (c.items[a], c.items[b]),
                    (c.items[b], c.items[a]),
                )
            )
    return pairs

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
    """
    if not items:
        return {}
    item_ids = [item.id for item in items]
    idx = {iid: i for i, iid in enumerate(item_ids)}
    n = len(items)

    pairs: list[tuple[int, int]] = []
    for c in comparisons:
        for winner, loser in _to_pairs(c):
            if winner in idx and loser in idx:
                pairs.append((idx[winner], idx[loser]))

    if not pairs:
        return {iid: Score(0.0, COLD_START_VARIANCE) for iid in item_ids}

    mean, cov = choix.ep_pairwise(n, pairs, alpha=PRIOR_ALPHA)
    variances = np.diag(cov)
    return {
        item_ids[i]: Score(float(mean[i]), float(variances[i]))
        for i in range(n)
    }


def select_cluster(
    scores: dict[str, Score],
    items: list[Item],
    max_k: int = 5,
    rng: random.Random | None = None,
    force_random_seed: bool = False,
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

    ``force_random_seed`` replaces the variance-greedy seed with a
    uniform pick *among the ``max_k`` most-uncertain items*, to escape
    fixed points without spuriously seeding on a well-separated item
    (which would always collapse to a singleton). The caller is
    expected to engage this every few rounds.
    """
    if max_k < MIN_K:
        raise ValueError(f"max_k must be at least {MIN_K}")
    if not items:
        return []

    rng = rng or random.Random()  # noqa: S311 (not security-sensitive)
    if force_random_seed:
        top_uncertain = sorted(
            items,
            key=lambda i: scores[i.id].variance,
            reverse=True,
        )[:max_k]
        seed = rng.choice(top_uncertain)
    else:
        seed = max(items, key=lambda i: scores[i.id].variance)
    seed_score = scores[seed.id]

    scored_candidates = [
        (_confusability(seed_score, scores[i.id]), i.id)
        for i in items
        if i.id != seed.id
    ]
    scored_candidates.sort(reverse=True)

    cluster = [seed.id]
    for conf, cand_id in scored_candidates:
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
    quantiles. Buckets remain monotonic in score.
    """
    if not scores:
        return {}
    sorted_ids = sorted(scores.keys(), key=lambda iid: scores[iid].mean)
    n = len(sorted_ids)
    if n == 1:
        return {sorted_ids[0]: n_quantiles - 1}
    return {
        iid: min(n_quantiles - 1, int(i / (n - 1) * n_quantiles))
        for i, iid in enumerate(sorted_ids)
    }


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

"""
Plackett-Luce inference, active cluster selection, quantile rescaling.

The ranking engine turns a list of :class:`Comparison` records into a
posterior distribution over Bradley-Terry / Plackett-Luce strengths,
and decides which items the user should be asked about next.
"""

from typing import NamedTuple
import random

import choix
import numpy as np

from great.models import Comparison, Item

PRIOR_ALPHA = 1.0
COLD_START_VARIANCE = 1.0 / PRIOR_ALPHA
CI_Z = 1.96
MIN_K = 2


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
    Pick a cluster of 2..``max_k`` items to compare next.

    Cold-start (items <= ``max_k``) returns everything; otherwise we
    seed on the highest-variance item and greedily grow the cluster
    by overlapping credible intervals. ``force_random_seed`` replaces
    the variance-greedy seed with a uniform pick to escape fixed
    points (the caller is expected to engage this every few rounds).
    """
    if max_k < MIN_K:
        raise ValueError(f"max_k must be at least {MIN_K}")
    if not items:
        return []
    if len(items) <= max_k:
        return [item.id for item in items]

    rng = rng or random.Random()  # noqa: S311 (not security-sensitive)
    seed = (
        rng.choice(items)
        if force_random_seed
        else max(
            items,
            key=lambda i: scores[i.id].variance,
        )
    )
    seed_score = scores[seed.id]
    seed_sd = seed_score.variance**0.5
    cluster_lo = seed_score.mean - CI_Z * seed_sd
    cluster_hi = seed_score.mean + CI_Z * seed_sd
    cluster = [seed.id]

    candidates = sorted(
        (i for i in items if i.id != seed.id),
        key=lambda i: scores[i.id].variance,
        reverse=True,
    )
    for cand in candidates:
        if len(cluster) >= max_k:
            break
        s = scores[cand.id]
        sd = s.variance**0.5
        cand_lo = s.mean - CI_Z * sd
        cand_hi = s.mean + CI_Z * sd
        if cand_hi >= cluster_lo and cand_lo <= cluster_hi:
            cluster.append(cand.id)
            cluster_lo = min(cluster_lo, cand_lo)
            cluster_hi = max(cluster_hi, cand_hi)

    if len(cluster) == 1:
        nearest = min(
            (i for i in items if i.id != seed.id),
            key=lambda i: abs(scores[i.id].mean - seed_score.mean),
        )
        cluster.append(nearest.id)

    return cluster


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

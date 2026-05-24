"""
Ranking-session protocol, scope, and driver.

A :class:`RankingScope` identifies where a ranking session reads from
and writes to -- either a favorites list (consumed catalog) or a
kind's want queue. The driver, :func:`run_rank_loop`, takes a scope
plus a session callable so it doesn't have to branch on storage
layout itself.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Self
import random
import textwrap

from great.models import Comparison, Item, ItemKind
from great.ranking import MIN_K, infer, select_cluster
from great.store import Store, items_file, want_file

RANDOM_SEED_EVERY = 5
RANK_MAX_ITERS_DEFAULT = 100
MAX_K = 5

SKIP: Literal["skip"] = "skip"
RankResult = list[list[int]] | Literal["skip"] | None
Session = Callable[[list[Item]], RankResult]


EXAMPLE_ITEM_BLOCK = """\
[[items]]
id = "tt0068646"        # any globally-unique id (IMDB, MusicBrainz, ...)
title = "The Godfather"
year = 1972             # optional
"""


class InsufficientItemsError(Exception):
    """A list has fewer than the minimum items needed to rank."""


@dataclass
class RankingScope:
    """
    Target for a ranking session: a favorites list or a want queue.

    Carries the items and comparisons known at scope construction
    along with how to append new comparisons. :func:`run_rank_loop`
    reads ``items`` / ``comparisons`` as the starting state and
    writes back via ``append_comparison``. ``how_to_add`` feeds the
    :class:`InsufficientItemsError` message when the scope is too
    sparse to rank.
    """

    items: list[Item]
    comparisons: list[Comparison]
    label: str
    how_to_add: str
    append_comparison: Callable[[Comparison], None]

    @classmethod
    def for_list(cls, store: Store, list_name: str) -> Self:
        """Build a scope for a configured favorites list."""
        list_config = store.list_config(list_name)
        return cls(
            items=store.items(list_config.kind),
            comparisons=store.comparisons(list_name),
            label=repr(list_name),
            how_to_add=(
                f"Add items to {items_file(list_config.kind)}, e.g.:\n\n"
                + textwrap.indent(EXAMPLE_ITEM_BLOCK.rstrip(), "  ")
            ),
            append_comparison=lambda c: store.append_comparison(list_name, c),
        )

    @classmethod
    def for_want(cls, store: Store, kind: ItemKind) -> Self:
        """Build a scope for a kind's want queue."""
        return cls(
            items=store.wants(kind),
            comparisons=store.want_comparisons(kind),
            label=f"want {kind!r}",
            how_to_add=(
                f"Add items via 'great want \"<title>\" --kind {kind}' "
                f"or by editing {want_file(kind)} directly."
            ),
            append_comparison=lambda c: store.append_want_comparison(kind, c),
        )


def run_rank_loop(
    scope: RankingScope,
    *,
    session: Session,
    max_iters: int = RANK_MAX_ITERS_DEFAULT,
    rng: random.Random | None = None,
    focus_ids: list[str] | None = None,
) -> int:
    """
    Drive a ranking session against ``scope``.

    The ``session`` callable is responsible for prompting the user
    (via TUI, scripted test fixture, or anything else); it receives
    the proposed cluster of items and returns either an ordering
    (list of tie groups), :data:`SKIP` to discard the cluster and
    request another, or ``None`` to end the session early. A skip
    forces the next iteration onto a random seed so the user is
    unlikely to be handed back the same cluster.

    ``focus_ids`` restricts cluster seeding to a subset of item ids
    (e.g. items just added via ``great add``): the loop keeps picking
    seeds from that set, never engages the random-seed jitter, and
    naturally ends as soon as every focus item is well-separated from
    the rest (``select_cluster`` returns a singleton).

    Raises :class:`InsufficientItemsError` when the scope has fewer
    than :data:`great.ranking.MIN_K` items. Returns the number of
    comparisons appended to the store.
    """
    if len(scope.items) < MIN_K:
        raise InsufficientItemsError(
            f"Need at least {MIN_K} items to rank {scope.label}, "
            f"found {len(scope.items)}.\n" + scope.how_to_add,
        )

    rng = rng or random.Random()  # noqa: S311 (not security-sensitive)
    items = list(scope.items)
    comparisons = list(scope.comparisons)
    by_id = {item.id: item for item in items}
    appended = 0
    force_random_next = False

    for iteration in range(max_iters):
        scores = infer(comparisons, items)
        force_random = force_random_next or (
            focus_ids is None
            and iteration > 0
            and iteration % RANDOM_SEED_EVERY == 0
        )
        force_random_next = False
        cluster_ids = select_cluster(
            scores,
            items,
            max_k=MAX_K,
            rng=rng,
            force_random_seed=force_random,
            seed_pool=focus_ids,
        )
        if len(cluster_ids) < MIN_K:
            break
        cluster_ids.sort(key=lambda i: scores[i].mean, reverse=True)
        cluster = [by_id[i] for i in cluster_ids]

        result = session(cluster)
        if result is None:
            break
        if result == SKIP:
            force_random_next = True
            continue

        c = Comparison(
            ts=datetime.now(UTC),
            items=cluster_ids,
            ordering=result,
        )
        scope.append_comparison(c)
        comparisons.append(c)
        appended += 1

    return appended


@dataclass
class AddOutcome:
    """One title's result from :func:`add_items`."""

    item: Item
    new: bool  # True if newly added, False if already present


@dataclass
class AddItemsResult:
    """Aggregate outcome of an :func:`add_items` call."""

    kind: ItemKind
    outcomes: list[AddOutcome]
    appended: int
    skipped_ranking: bool  # True iff items were added but MIN_K was not met


def add_items(
    store: Store,
    list_name: str,
    titles: list[str],
    *,
    session: Session,
    max_iters: int = RANK_MAX_ITERS_DEFAULT,
) -> AddItemsResult:
    """
    Append ``titles`` to ``list_name``'s catalog and rank them in.

    For each title an :class:`Item` is built (id defaults to the
    title) and appended via :meth:`Store.add_item`; duplicates are
    recorded in the result's ``outcomes`` with ``new=False``. If
    anything was newly added, the new ids drive a focused ranking
    session (``focus_ids``). If the catalog still has too few items
    to rank, the :class:`InsufficientItemsError` is caught and
    surfaced as ``skipped_ranking=True`` in the result.

    Returns an :class:`AddItemsResult` describing each title's
    outcome and how the ranking attempt resolved.
    """
    list_config = store.list_config(list_name)
    kind = list_config.kind
    outcomes: list[AddOutcome] = []
    new_ids: list[str] = []
    for title in titles:
        item = Item.from_dict({"title": title}, kind=kind)
        new = store.add_item(item)
        outcomes.append(AddOutcome(item=item, new=new))
        if new:
            new_ids.append(item.id)
    if not new_ids:
        return AddItemsResult(
            kind=kind,
            outcomes=outcomes,
            appended=0,
            skipped_ranking=False,
        )
    scope = RankingScope.for_list(store, list_name)
    try:
        appended = run_rank_loop(
            scope,
            session=session,
            max_iters=max_iters,
            focus_ids=new_ids,
        )
    except InsufficientItemsError:
        return AddItemsResult(
            kind=kind,
            outcomes=outcomes,
            appended=0,
            skipped_ranking=True,
        )
    return AddItemsResult(
        kind=kind,
        outcomes=outcomes,
        appended=appended,
        skipped_ranking=False,
    )

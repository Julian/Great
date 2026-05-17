"""
Look up an item in a Great data repo by id, exact title, or external id.
"""

from great.models import Item, ItemKind
from great.store import Store


class ItemNotFoundError(Exception):
    """No item matched the given lookup query."""


class AmbiguousItemError(Exception):
    """Multiple items matched the given lookup query."""


def matches(item: Item, query: str) -> bool:
    """Match an item by exact id, case-insensitive title, or external id."""
    return (
        item.id == query
        or item.title.casefold() == query.casefold()
        or query in item.external_ids.values()
    )


def resolve_item(
    store: Store,
    query: str,
    kind: ItemKind | None = None,
    *,
    search_catalog: bool = True,
    search_wants: bool = False,
) -> Item:
    """
    Find an item by id, exact (case-insensitive) title, or external id.

    ``kind`` restricts the search to a single kind; ``None`` (default)
    spans every kind declared in the store config. The two boolean
    flags choose the source(s) to search: by default only the consumed
    catalog. ``great log`` enables ``search_wants`` so that consuming
    a wanted item promotes it; ``great unwant`` flips both flags to
    search the want queue alone.

    Raises :class:`ItemNotFoundError` if no item matched, or
    :class:`AmbiguousItemError` if more than one did.
    """
    if not (search_catalog or search_wants):
        raise ValueError(
            "at least one of search_catalog/search_wants must be True",
        )
    kinds: set[ItemKind] = (
        {kind} if kind else {lst.kind for lst in store.config.lists}
    )
    candidates: list[Item] = []
    for k in kinds:
        sources: list[list[Item]] = []
        if search_catalog:
            sources.append(store.items(k))
        if search_wants:
            sources.append(store.wants(k))
        candidates.extend(
            item
            for source in sources
            for item in source
            if matches(item, query)
        )
    if not candidates:
        raise ItemNotFoundError(f"no item matching {query!r}")
    if len(candidates) > 1:
        listed = ", ".join(
            f"{i.title!r} (kind={i.kind}, id={i.id})" for i in candidates
        )
        raise AmbiguousItemError(
            f"{query!r} matches {len(candidates)} items: {listed}. "
            "Pass --kind or use an exact id.",
        )
    return candidates[0]

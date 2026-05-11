"""Command-line interface for Great."""

from collections.abc import Iterator
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Any, get_args
import contextlib
import random
import textwrap

import typer

from great.models import (
    KIND_PLURAL,
    Comparison,
    GreatConfig,
    Item,
    ItemKind,
    ListConfig,
    LogEntry,
    LogStatus,
)
from great.ranking import MIN_K, infer, rescale_to_quantiles, select_cluster
from great.render import N_QUANTILES, build_site, rank_by_score, tier_label
from great.store import (
    ListNotFoundError,
    Store,
    StoreError,
    StoreNotFoundError,
)
from great.tui import Session, run_rank_session

RANDOM_SEED_EVERY = 5
RANK_MAX_ITERS_DEFAULT = 100
MAX_K = 5

ITEM_KINDS = ", ".join(get_args(ItemKind))

DEFAULT_LISTS: tuple[ListConfig, ...] = (
    ListConfig(name="movies", kind="movie"),
    ListConfig(name="tv", kind="tv"),
    ListConfig(name="artists", kind="artist"),
    ListConfig(name="albums", kind="album"),
    ListConfig(name="songs", kind="song"),
    ListConfig(name="books", kind="book"),
    ListConfig(name="podcasts", kind="podcast"),
    ListConfig(name="games", kind="game"),
)

EXAMPLE_ITEM_BLOCK = """\
[[items]]
id = "tt0068646"        # any globally-unique id (IMDB, MusicBrainz, ...)
title = "The Godfather"
year = 1972             # optional
"""


def _example_items_toml(kind: ItemKind) -> str:
    """Body for an empty items file with a commented schema example."""
    header = f"# Items of kind `{kind}` go here, one [[items]] table each.\n"
    body = (
        "# Required key per item: `title`. Optional: `id` (defaults to\n"
        "# the title), `year`, `external_ids`, `metadata`. The `kind` is\n"
        "# implied by the filename and must not appear inside [[items]].\n"
        "#\n"
    )
    commented = "".join(
        (f"# {line}\n" if line else "#\n")
        for line in EXAMPLE_ITEM_BLOCK.splitlines()
    )
    return header + body + commented


PAGES_WORKFLOW = (
    files("great._data")
    .joinpath("pages_workflow.yml")
    .read_text(
        encoding="utf-8",
    )
)


class InsufficientItemsError(Exception):
    """A list has fewer than the minimum items needed to rank."""


class ItemNotFoundError(Exception):
    """No item matched the given lookup query."""


class AmbiguousItemError(Exception):
    """Multiple items matched the given lookup query."""


_FRIENDLY = (
    AmbiguousItemError,
    InsufficientItemsError,
    ItemNotFoundError,
    ListNotFoundError,
    StoreError,
    StoreNotFoundError,
)


@contextlib.contextmanager
def _friendly_errors() -> Iterator[None]:
    """Convert known domain errors into a clean stderr + exit 1."""
    try:
        yield
    except _FRIENDLY as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from e


app = typer.Typer(
    name="great",
    no_args_is_help=True,
    help="Track and rank personal media via pairwise/k-way comparison.",
)


def main() -> None:
    """Run the CLI as a console-script entry point."""
    app()


@app.callback()
def _root(
    ctx: typer.Context,
    root: Annotated[
        Path | None,
        typer.Option(
            "--root",
            help="Path to the data repo (defaults to walking up from cwd).",
        ),
    ] = None,
) -> None:
    """Track and rank personal media via pairwise/k-way comparison."""
    ctx.obj = root


@app.command()
def show(
    ctx: typer.Context,
    target: Annotated[
        str,
        typer.Argument(
            help="List name (favorites) or item kind (with --want).",
        ),
    ],
    want: Annotated[
        bool,
        typer.Option(
            "--want/--no-want",
            help="Show the want-to-watch ranking for the given kind.",
        ),
    ] = False,
) -> None:
    """Print the inferred ranking for a list (or for --want <kind>)."""
    with _friendly_errors():
        store = Store.find(ctx.obj)
        if want:
            kind = _parse_kind(target)
            items = store.wants(kind)
            comparisons = store.want_comparisons(kind)
        else:
            list_config = store.list_config(target)
            items = store.items(list_config.kind)
            comparisons = store.comparisons(target)
        scores = infer(comparisons, items)
        if not items:
            return
        # Tiers are quality strata for consumed items; the want ranking
        # is watch-order priority, where D..S labels would mislead.
        tiers = (
            {
                iid: tier_label(q)
                for iid, q in rescale_to_quantiles(
                    scores,
                    n_quantiles=N_QUANTILES,
                ).items()
            }
            if comparisons and not want
            else {}
        )
        for rank_, item in enumerate(rank_by_score(items, scores), start=1):
            s = scores[item.id]
            suffix = f" ({item.year})" if item.year is not None else ""
            tier = f"[{tiers[item.id]}] " if item.id in tiers else ""
            typer.echo(
                f"{rank_:3d}. {tier}{item.title}{suffix}  "
                f"score={s.mean:+.2f} sd={s.variance**0.5:.2f}",
            )


def _parse_kind(value: str) -> ItemKind:
    """Validate a string against the ItemKind literal type."""
    for kind in get_args(ItemKind):
        if value == kind:
            return kind
    raise typer.BadParameter(
        f"{value!r} is not a valid kind. Choose one of: {ITEM_KINDS}.",
    )


@app.command(name="lists")
def lists_(ctx: typer.Context) -> None:
    """Print the lists configured in ``great.toml``."""
    with _friendly_errors():
        store = Store.find(ctx.obj)
        if not store.config.lists:
            typer.echo("No lists configured. Add some to great.toml.")
            return
        for lst in store.config.lists:
            suffix = f" — {lst.description}" if lst.description else ""
            typer.echo(f"{lst.name}  ({lst.kind}){suffix}")


@app.command()
def diary(
    ctx: typer.Context,
    year: Annotated[
        int | None,
        typer.Option("--year", help="Restrict to a single year."),
    ] = None,
) -> None:
    """Print the consumption diary, most recent first."""
    with _friendly_errors():
        store = Store.find(ctx.obj)
        entries = sorted(
            store.log(year=year),
            key=lambda e: e.ts,
            reverse=True,
        )
        if not entries:
            typer.echo("No diary entries.")
            return
        kinds = {lst.kind for lst in store.config.lists}
        titles = {
            (i.kind, i.id): i.title
            for k in kinds
            for i in [*store.items(k), *store.wants(k)]
        }
        for e in entries:
            title = titles.get((e.kind, e.item), e.item)
            tail = f" — {e.notes}" if e.notes else ""
            typer.echo(
                f"{e.ts.date()}  {title} ({e.kind})  {e.status}{tail}",
            )


@app.command()
def rank(
    ctx: typer.Context,
    target: Annotated[
        str,
        typer.Argument(
            help="List name (favorites) or item kind (with --want).",
        ),
    ],
    want: Annotated[
        bool,
        typer.Option(
            "--want/--no-want",
            help="Rank the want-to-watch queue for the given kind.",
        ),
    ] = False,
    max_iters: Annotated[
        int,
        typer.Option(
            "--max-iters",
            help="Stop after this many comparisons in one session.",
        ),
    ] = RANK_MAX_ITERS_DEFAULT,
) -> None:
    """Run an interactive ranking session in the Textual TUI."""
    with _friendly_errors():
        store = Store.find(ctx.obj)
        run_rank_loop(
            store,
            target,
            want=want,
            session=run_rank_session,
            max_iters=max_iters,
        )


def run_rank_loop(
    store: Store,
    target: str,
    *,
    want: bool = False,
    session: Session,
    max_iters: int = RANK_MAX_ITERS_DEFAULT,
    rng: random.Random | None = None,
) -> int:
    """
    Drive a ranking session against ``store``.

    The ``session`` callable is responsible for prompting the user
    (via TUI, scripted test fixture, or anything else); it receives
    the proposed cluster of items and returns either an ordering
    (list of tie groups) or ``None`` to end the session early.

    With ``want=True``, ``target`` is interpreted as an item kind and
    the session ranks that kind's want queue; comparisons are routed
    to ``comparisons/want/<kind>.jsonl``. Otherwise ``target`` is a
    list name as declared in ``great.toml``.

    Returns the number of comparisons appended to the store.
    """
    if want:
        kind = _parse_kind(target)
        items = store.wants(kind)
        comparisons = list(store.want_comparisons(kind))
        scope_label = f"want {kind!r}"
        how_to_add = (
            f"Add items via 'great want \"<title>\" --kind {kind}' "
            f"or by editing want/{KIND_PLURAL[kind]}.toml directly."
        )
    else:
        list_config = store.list_config(target)
        items = store.items(list_config.kind)
        comparisons = list(store.comparisons(target))
        scope_label = repr(target)
        items_file = f"items/{KIND_PLURAL[list_config.kind]}.toml"
        how_to_add = f"Add items to {items_file}, e.g.:\n\n" + textwrap.indent(
            EXAMPLE_ITEM_BLOCK.rstrip(), "  "
        )

    if len(items) < MIN_K:
        raise InsufficientItemsError(
            f"Need at least {MIN_K} items to rank {scope_label}, "
            f"found {len(items)}.\n" + how_to_add,
        )

    rng = rng or random.Random()  # noqa: S311 (not security-sensitive)
    by_id = {item.id: item for item in items}
    appended = 0

    for iteration in range(max_iters):
        scores = infer(comparisons, items)
        force_random = iteration > 0 and iteration % RANDOM_SEED_EVERY == 0
        cluster_ids = select_cluster(
            scores,
            items,
            max_k=MAX_K,
            rng=rng,
            force_random_seed=force_random,
        )
        if len(cluster_ids) < MIN_K:
            break
        cluster_ids.sort(key=lambda i: scores[i].mean, reverse=True)
        cluster = [by_id[i] for i in cluster_ids]

        result = session(cluster)
        if result is None:
            break

        c = Comparison(
            ts=datetime.now(UTC),
            items=cluster_ids,
            ordering=result,
        )
        if want:
            store.append_want_comparison(kind, c)
        else:
            store.append_comparison(target, c)
        comparisons.append(c)
        appended += 1

    return appended


def _matches(item: Item, query: str, folded_query: str) -> bool:
    """Lookup predicate: exact id, case-insensitive title, or external id."""
    return (
        item.id == query
        or item.title.casefold() == folded_query
        or query in item.external_ids.values()
    )


def resolve_item(
    store: Store,
    query: str,
    kind: ItemKind | None = None,
    *,
    include_wants: bool = False,
) -> Item:
    """
    Find an item by id, exact (case-insensitive) title, or external id.

    By default only the consumed catalog is searched. With
    ``include_wants=True`` the want queue is searched too — used by
    ``great log`` so that consuming a wanted item promotes it.
    """
    kinds: set[ItemKind] = (
        {kind} if kind else {lst.kind for lst in store.config.lists}
    )
    folded = query.casefold()
    candidates: list[Item] = []
    for k in kinds:
        sources = [store.items(k)]
        if include_wants:
            sources.append(store.wants(k))
        candidates.extend(
            item
            for source in sources
            for item in source
            if _matches(item, query, folded)
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


def _resolve_ts(at: datetime | None) -> datetime:
    """Return ``at`` (UTC-anchored) or now."""
    if at is None:
        return datetime.now(UTC)
    return at if at.tzinfo else at.replace(tzinfo=UTC)


@app.command(name="log")
def log_(
    ctx: typer.Context,
    item: Annotated[str, typer.Argument(help="Item id or exact title.")],
    status: Annotated[
        LogStatus,
        typer.Option("--status", help="consumed, started, or abandoned."),
    ] = "consumed",
    notes: Annotated[
        str | None,
        typer.Option("--notes", help="Optional free-form notes."),
    ] = None,
    at: Annotated[
        datetime | None,
        typer.Option(
            "--at",
            help="When this happened (ISO date or datetime). Defaults to now.",
        ),
    ] = None,
    kind: Annotated[
        ItemKind | None,
        typer.Option("--kind", help="Restrict lookup to a single kind."),
    ] = None,
) -> None:
    """Append a consumption-diary entry."""
    with _friendly_errors():
        store = Store.find(ctx.obj)
        resolved = resolve_item(store, item, kind=kind, include_wants=True)
        promoted = (
            status == "consumed"
            and store.promote_want(resolved.kind, resolved.id) is not None
        )
        store.append_log(
            LogEntry(
                ts=_resolve_ts(at),
                kind=resolved.kind,
                item=resolved.id,
                status=status,
                notes=notes,
            ),
        )
        typer.echo(f"Logged {status}: {resolved.title}")
        if promoted:
            typer.echo("  (promoted from want queue)")


@app.command()
def consumed(
    ctx: typer.Context,
    item: Annotated[str, typer.Argument(help="Item id or exact title.")],
    notes: Annotated[
        str | None,
        typer.Option("--notes", help="Optional free-form notes."),
    ] = None,
    at: Annotated[
        datetime | None,
        typer.Option(
            "--at",
            help="When this happened (ISO date or datetime). Defaults to now.",
        ),
    ] = None,
    kind: Annotated[
        ItemKind | None,
        typer.Option("--kind", help="Restrict lookup to a single kind."),
    ] = None,
) -> None:
    """Shortcut for ``great log <item> --status consumed``."""
    log_(ctx, item, status="consumed", notes=notes, at=at, kind=kind)


@app.command()
def want(
    ctx: typer.Context,
    title: Annotated[
        str,
        typer.Argument(help="Title of the item to add to the want queue."),
    ],
    kind: Annotated[
        ItemKind,
        typer.Option("--kind", help=f"Item kind ({ITEM_KINDS})."),
    ],
    year: Annotated[
        int | None,
        typer.Option("--year", help="Release year (optional)."),
    ] = None,
    id_: Annotated[
        str | None,
        typer.Option(
            "--id",
            help="Override the item id (defaults to the title).",
        ),
    ] = None,
) -> None:
    """Add a free-form title to the want-to-consume queue for ``kind``."""
    with _friendly_errors():
        store = Store.find(ctx.obj)
        data: dict[str, Any] = {"title": title}
        if id_ is not None:
            data["id"] = id_
        if year is not None:
            data["year"] = year
        item = Item.from_dict(data, kind=kind)
        added = store.add_want(item)
        verb = "Added to" if added else "Already on"
        typer.echo(f"{verb} want/{KIND_PLURAL[kind]}: {item.title}")


@app.command()
def unwant(
    ctx: typer.Context,
    item: Annotated[str, typer.Argument(help="Item id or exact title.")],
    kind: Annotated[
        ItemKind | None,
        typer.Option("--kind", help="Restrict lookup to a single kind."),
    ] = None,
) -> None:
    """Remove an item from its kind's want queue."""
    with _friendly_errors():
        store = Store.find(ctx.obj)
        kinds: set[ItemKind] = (
            {kind} if kind else {lst.kind for lst in store.config.lists}
        )
        folded = item.casefold()
        matches: list[tuple[ItemKind, Item]] = [
            (k, w)
            for k in kinds
            for w in store.wants(k)
            if _matches(w, item, folded)
        ]
        if not matches:
            typer.echo(f"Not on any want queue: {item}")
            return
        if len(matches) > 1:
            listed = ", ".join(
                f"{w.title!r} (kind={k}, id={w.id})" for k, w in matches
            )
            raise AmbiguousItemError(
                f"{item!r} matches {len(matches)} want entries: {listed}. "
                "Pass --kind or use an exact id.",
            )
        [(matched_kind, matched)] = matches
        store.remove_want(matched_kind, matched.id)
        typer.echo(
            f"Removed from want/{KIND_PLURAL[matched_kind]}: {matched.title}"
        )


@app.command()
def build(
    ctx: typer.Context,
    out: Annotated[
        Path | None,
        typer.Option(
            "--out",
            help="Output directory (defaults to <repo>/dist).",
        ),
    ] = None,
) -> None:
    """Render the static site to ``out``."""
    with _friendly_errors():
        store = Store.find(ctx.obj)
        target = out if out is not None else store.root / "dist"
        build_site(store, target)
        typer.echo(f"Built site → {target}")


def _parse_list_spec(spec: str) -> ListConfig:
    """Parse a ``name:kind`` spec from the CLI."""
    if ":" not in spec:
        msg = f"expected NAME:KIND, got {spec!r}"
        raise typer.BadParameter(msg)
    name, _, kind = spec.partition(":")
    return ListConfig.model_validate({"name": name, "kind": kind})


@app.command()
def init(
    path: Annotated[
        Path,
        typer.Argument(help="Where to create the data repo."),
    ] = Path(),
    list_specs: Annotated[
        list[str] | None,
        typer.Option(
            "--list",
            "-l",
            metavar="NAME:KIND",
            help=(
                "Declare a list, given as NAME:KIND (repeatable). "
                "NAME is yours to pick (e.g. 'movies', 'top-films'); "
                f"KIND is one of: {ITEM_KINDS}. "
                "Each kind has a single shared want-to-consume queue at "
                "want/<kind>.toml (independent of how many favorite-lists "
                "you configure for that kind). "
                "If omitted, one list per kind is seeded with default names."
            ),
        ),
    ] = None,
    with_pages: Annotated[
        bool,
        typer.Option(
            "--with-pages/--no-pages",
            help="Drop a GitHub Actions Pages-deploy workflow.",
        ),
    ] = True,
) -> None:
    """Bootstrap a new data repo at ``path``."""
    if (path / "great.toml").exists():
        typer.echo(f"{path / 'great.toml'} already exists.", err=True)
        raise typer.Exit(1)
    try:
        lists = [_parse_list_spec(s) for s in list_specs or []]
    except (typer.BadParameter, ValueError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from e
    if not lists:
        lists = list(DEFAULT_LISTS)
    Store.init(path, GreatConfig(lists=lists))
    for kind in {lst.kind for lst in lists}:
        (path / "items" / f"{KIND_PLURAL[kind]}.toml").write_text(
            _example_items_toml(kind),
        )
    if with_pages:
        workflow = path / ".github" / "workflows" / "build.yml"
        workflow.parent.mkdir(parents=True, exist_ok=True)
        workflow.write_text(PAGES_WORKFLOW)
    typer.echo(f"Initialized data repo at {path.resolve()}")
    names = ", ".join(lst.name for lst in lists)
    typer.echo(f"Lists: {names}")
    typer.echo(
        "Add items to items/, then `great rank <list>` to start ranking.",
    )

"""Command-line interface for Great."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
import contextlib
import random

import typer

from great.models import (
    Comparison,
    GreatConfig,
    Item,
    ItemKind,
    ListConfig,
    LogEntry,
    LogStatus,
    Priority,
    WantEntry,
)
from great.ranking import MIN_K, infer, rescale_to_quantiles, select_cluster
from great.render import N_QUANTILES, build_site, tier_label
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

PAGES_WORKFLOW = """\
name: build-and-deploy

on:
  push:
    branches: [main, master]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          enable-cache: true
      - run: uv tool install git+https://github.com/Julian/Great
      - run: great build
      - uses: actions/upload-pages-artifact@v3
        with:
          path: dist

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
"""


class InsufficientItemsError(Exception):
    """A list has fewer than the minimum items needed to rank."""


class ItemNotFoundError(Exception):
    """No item matched the given lookup query."""


class AmbiguousItemError(Exception):
    """Multiple items matched the given lookup query."""


class NoWantListError(Exception):
    """No unique want list could be inferred for an item's kind."""


_FRIENDLY = (
    AmbiguousItemError,
    InsufficientItemsError,
    ItemNotFoundError,
    ListNotFoundError,
    NoWantListError,
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
    list_name: Annotated[
        str,
        typer.Argument(help="Name of the list to show."),
    ],
) -> None:
    """Print the inferred ranking for a list."""
    with _friendly_errors():
        store = Store.find(ctx.obj)
        list_config = store.list_config(list_name)
        items = store.items(list_config.kind)
        comparisons = store.comparisons(list_name)
        scores = infer(comparisons, items)
        if not items:
            return
        tiers = (
            {
                iid: tier_label(q)
                for iid, q in rescale_to_quantiles(
                    scores,
                    n_quantiles=N_QUANTILES,
                ).items()
            }
            if comparisons
            else {}
        )
        by_score = sorted(
            items,
            key=lambda i: (-scores[i.id].mean, i.title.casefold()),
        )
        for rank_, item in enumerate(by_score, start=1):
            s = scores[item.id]
            suffix = f" ({item.year})" if item.year is not None else ""
            tier = f"[{tiers[item.id]}] " if item.id in tiers else ""
            typer.echo(
                f"{rank_:3d}. {tier}{item.title}{suffix}  "
                f"score={s.mean:+.2f} sd={s.variance**0.5:.2f}",
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
def rank(
    ctx: typer.Context,
    list_name: Annotated[
        str,
        typer.Argument(help="Name of the list to rank."),
    ],
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
            list_name,
            session=run_rank_session,
            max_iters=max_iters,
        )


def run_rank_loop(
    store: Store,
    list_name: str,
    *,
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

    Returns the number of comparisons appended to the store.
    """
    list_config = store.list_config(list_name)
    items = store.items(list_config.kind)
    if len(items) < MIN_K:
        raise InsufficientItemsError(
            f"Need at least {MIN_K} items to rank, found {len(items)}.",
        )

    rng = rng or random.Random()  # noqa: S311 (not security-sensitive)
    comparisons = list(store.comparisons(list_name))
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
        cluster = [by_id[i] for i in cluster_ids]

        result = session(cluster)
        if result is None:
            break

        c = Comparison(
            ts=datetime.now(UTC),
            list=list_name,
            items=cluster_ids,
            ordering=result,
        )
        store.append_comparison(c)
        comparisons.append(c)
        appended += 1

    return appended


def resolve_item(
    store: Store,
    query: str,
    kind: ItemKind | None = None,
) -> Item:
    """Find an item by id or exact (case-insensitive) title."""
    kinds: set[ItemKind] = (
        {kind} if kind else {lst.kind for lst in store.config.lists}
    )
    candidates = [
        item
        for k in kinds
        for item in store.items(k)
        if item.id == query or item.title.casefold() == query.casefold()
    ]
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


def infer_want_list(store: Store, kind: ItemKind) -> str:
    """Return the unique configured list for ``kind``, or raise."""
    candidates = [lst.name for lst in store.config.lists if lst.kind == kind]
    if not candidates:
        raise NoWantListError(
            f"no list configured for kind {kind!r}. "
            "Add one to great.toml or pass --list.",
        )
    if len(candidates) > 1:
        raise NoWantListError(
            f"multiple lists for kind {kind!r}: {', '.join(candidates)}. "
            "Pass --list to disambiguate.",
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
        resolved = resolve_item(store, item, kind=kind)
        store.append_log(
            LogEntry(
                ts=_resolve_ts(at),
                item=resolved.id,
                status=status,
                notes=notes,
            ),
        )
        pruned = store.discard_from_wants(resolved.id)
        typer.echo(f"Logged {status}: {resolved.title}")
        if pruned:
            suffix = "s" if pruned > 1 else ""
            typer.echo(f"  (removed from {pruned} want list{suffix})")


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
    item: Annotated[str, typer.Argument(help="Item id or exact title.")],
    list_name: Annotated[
        str | None,
        typer.Option(
            "--list",
            "-l",
            help="Want list (defaults to the unique list for the kind).",
        ),
    ] = None,
    priority: Annotated[
        Priority,
        typer.Option("--priority", "-p"),
    ] = "normal",
    kind: Annotated[
        ItemKind | None,
        typer.Option("--kind", help="Restrict lookup to a single kind."),
    ] = None,
) -> None:
    """Add an item to a want-to-consume queue."""
    with _friendly_errors():
        store = Store.find(ctx.obj)
        resolved = resolve_item(store, item, kind=kind)
        target = list_name or infer_want_list(store, resolved.kind)
        store.add_want(
            target,
            WantEntry(
                item=resolved.id,
                added=datetime.now(UTC).date(),
                priority=priority,
            ),
        )
        typer.echo(f"Added to {target!r}: {resolved.title}")


@app.command()
def unwant(
    ctx: typer.Context,
    item: Annotated[str, typer.Argument(help="Item id or exact title.")],
    list_name: Annotated[
        str | None,
        typer.Option(
            "--list",
            "-l",
            help="Want list (defaults to all that contain the item).",
        ),
    ] = None,
    kind: Annotated[
        ItemKind | None,
        typer.Option("--kind", help="Restrict lookup to a single kind."),
    ] = None,
) -> None:
    """Remove an item from one or all want queues."""
    with _friendly_errors():
        store = Store.find(ctx.obj)
        resolved = resolve_item(store, item, kind=kind)
        if list_name is None:
            removed = store.discard_from_wants(resolved.id)
        else:
            removed = int(store.remove_want(list_name, resolved.id))
        if removed:
            suffix = "s" if removed > 1 else ""
            typer.echo(
                f"Removed from {removed} want list{suffix}: {resolved.title}",
            )
        else:
            typer.echo(f"Not on any want list: {resolved.title}")


@app.command()
def build(
    ctx: typer.Context,
    out: Annotated[
        Path,
        typer.Option("--out", help="Output directory."),
    ] = Path("dist"),
) -> None:
    """Render the static site to ``out``."""
    with _friendly_errors():
        store = Store.find(ctx.obj)
        build_site(store, out)
        typer.echo(f"Built site → {out}")


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
            help="Declare a list as NAME:KIND (repeatable).",
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
    Store.init(path, GreatConfig(lists=lists))
    if with_pages:
        workflow = path / ".github" / "workflows" / "build.yml"
        workflow.parent.mkdir(parents=True, exist_ok=True)
        workflow.write_text(PAGES_WORKFLOW)
    typer.echo(f"Initialized data repo at {path.resolve()}")
    if not lists:
        typer.echo(
            "Edit great.toml to add lists, then `great rank <list>` to start.",
        )

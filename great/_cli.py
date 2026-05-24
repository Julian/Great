"""Command-line interface for Great."""

from collections.abc import Iterator
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Any, get_args
import contextlib

import typer

from great.albumsgenerator import (
    SOURCE_KEY as ALBUMSGENERATOR_SOURCE_KEY,
    AlbumsGeneratorError,
    fetch_project,
    revealed_counts,
    save_project,
)
from great.antennapod import (
    EXPECTED_SCHEMA_VERSION,
    AntennaPodError,
    counts as antennapod_counts,
    read_export,
    save_export,
)
from great.lookup import (
    AmbiguousItemError,
    ItemNotFoundError,
    resolve_item,
)
from great.models import (
    KIND_PLURAL,
    PARENT_KIND,
    GreatConfig,
    Item,
    ItemKind,
    ListConfig,
    LogEntry,
    LogStatus,
)
from great.ranking import MIN_K, infer, rescale_to_quantiles
from great.render import N_QUANTILES, build_site, rank_by_score, tier_label
from great.session import (
    EXAMPLE_ITEM_BLOCK,
    RANK_MAX_ITERS_DEFAULT,
    InsufficientItemsError,
    RankingScope,
    add_items,
    run_rank_loop,
)
from great.store import (
    ListNotFoundError,
    Store,
    StoreError,
    StoreNotFoundError,
)
from great.tui import run_rank_session

ITEM_KINDS = ", ".join(get_args(ItemKind))

DEFAULT_LISTS: tuple[ListConfig, ...] = (
    ListConfig(name="movies", kind="movie"),
    ListConfig(name="tv", kind="tv"),
    ListConfig(name="artists", kind="artist"),
    ListConfig(name="albums", kind="album"),
    ListConfig(name="songs", kind="song"),
    ListConfig(name="books", kind="book"),
    ListConfig(name="podcasts", kind="podcast"),
    ListConfig(name="podcast_episodes", kind="podcast_episode"),
    ListConfig(name="games", kind="game"),
)


def _example_items_toml(kind: ItemKind) -> str:
    """Body for an empty items file with a commented schema example."""
    header = f"# Items of kind `{kind}` go here, one [[items]] table each.\n"
    parent = PARENT_KIND.get(kind)
    parent_clause = (
        f", `parent_id` (the id of the parent {parent})" if parent else ""
    )
    body = (
        "# Required key per item: `title`. Optional: `id` (defaults to\n"
        "# the title), `year`, `creators`, `external_ids`, `metadata`"
        f"{parent_clause}.\n"
        "# The `kind` is implied by the filename and must not appear\n"
        "# inside [[items]].\n"
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


_FRIENDLY = (
    AlbumsGeneratorError,
    AntennaPodError,
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
import_app = typer.Typer(
    no_args_is_help=True,
    help="Import data from external sources into the consumed catalog.",
)
app.add_typer(import_app, name="import")


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
        scope = _scope_for(store, target, want=want)
        scores = infer(scope.comparisons, scope.items)
        if not scope.items:
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
            if scope.comparisons and not want
            else {}
        )
        for rank_, item in enumerate(
            rank_by_score(scope.items, scores),
            start=1,
        ):
            s = scores[item.id]
            suffix = f" ({item.year})" if item.year is not None else ""
            tier = f"[{tiers[item.id]}] " if item.id in tiers else ""
            byline = (
                typer.style(", ".join(item.creators), italic=True, dim=True)
                + " "
                if item.creators
                else ""
            )
            typer.echo(
                f"{rank_:3d}. {tier}{byline}{item.title}{suffix}  "
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


def _scope_for(store: Store, target: str, *, want: bool) -> RankingScope:
    """Build the :class:`RankingScope` for a CLI ``target``/``--want`` pair."""
    if want:
        return RankingScope.for_want(store, _parse_kind(target))
    return RankingScope.for_list(store, target)


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
def add(
    ctx: typer.Context,
    list_name: Annotated[
        str,
        typer.Argument(help="List name (favorites) to add the items to."),
    ],
    titles: Annotated[
        list[str],
        typer.Argument(help="One or more titles to add to the list."),
    ],
    max_iters: Annotated[
        int,
        typer.Option(
            "--max-iters",
            help="Stop after this many comparisons in one session.",
        ),
    ] = RANK_MAX_ITERS_DEFAULT,
) -> None:
    """
    Add items to a favorites list, then place them via ranking.

    Each title is appended to ``items/<kind>.toml`` (with an id
    defaulting to the title); duplicates are skipped with a note.
    After adding, runs a focused ranking session that keeps seeding on
    the newly-added items until they're well-separated from the rest.
    """
    with _friendly_errors():
        store = Store.find(ctx.obj)
        result = add_items(
            store,
            list_name,
            titles,
            session=run_rank_session,
            max_iters=max_iters,
        )
        for outcome in result.outcomes:
            verb = "Added to" if outcome.new else "Already in"
            typer.echo(
                f"{verb} items/{KIND_PLURAL[result.kind]}: "
                f"{outcome.item.title}",
            )
        if result.skipped_ranking:
            typer.echo(
                f"Need at least {MIN_K} items to rank {list_name!r}, "
                f"found {len(store.items(result.kind))}. "
                "Skipping ranking session.",
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
            _scope_for(store, target, want=want),
            session=run_rank_session,
            max_iters=max_iters,
        )


def _resolve_ts(at: datetime | None) -> datetime:
    """Return ``at`` (UTC-anchored) or now."""
    if at is None:
        return datetime.now(UTC)
    return at if at.tzinfo else at.replace(tzinfo=UTC)


def _record_log_entry(
    store: Store,
    query: str,
    *,
    status: LogStatus,
    notes: str | None,
    at: datetime | None,
    kind: ItemKind | None,
) -> None:
    """Resolve ``query``, promote-on-consume, and append the diary entry."""
    resolved = resolve_item(store, query, kind=kind, search_wants=True)
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
        _record_log_entry(
            store,
            item,
            status=status,
            notes=notes,
            at=at,
            kind=kind,
        )


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
    with _friendly_errors():
        store = Store.find(ctx.obj)
        _record_log_entry(
            store,
            item,
            status="consumed",
            notes=notes,
            at=at,
            kind=kind,
        )


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
        try:
            resolved = resolve_item(
                store,
                item,
                kind=kind,
                search_catalog=False,
                search_wants=True,
            )
        except ItemNotFoundError:
            typer.echo(f"Not on any want queue: {item}")
            return
        store.remove_want(resolved.kind, resolved.id)
        typer.echo(
            f"Removed from want/{KIND_PLURAL[resolved.kind]}: {resolved.title}"
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


@import_app.command("1001albums")
def import_1001albums(
    ctx: typer.Context,
    username: Annotated[
        str | None,
        typer.Argument(
            help=(
                "1001albumsgenerator.com username. If omitted, reads from "
                "[sources.albumsgenerator] in great.toml. The username is "
                "persisted on first successful import."
            ),
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show what would be imported without writing.",
        ),
    ] = False,
) -> None:
    """
    Fetch a 1001albums project and save it as a catalog source.

    The raw project JSON is cached at ``sources/albumsgenerator.json``.
    The derived catalog (read by ranking, render, and ``great show``)
    picks it up on the next read — each revealed album becomes an
    album item, each consumed-status diary entry is synthesized from
    the reveal timestamp, and the album's artist is auto-added to the
    artist catalog. Re-running just refreshes the cache.
    """
    with _friendly_errors():
        store = Store.find(ctx.obj)
        configured = store.config.sources.get(
            ALBUMSGENERATOR_SOURCE_KEY,
            {},
        ).get("username")
        resolved_username = username or configured
        if not resolved_username:
            typer.echo(
                "No username given and none in great.toml. Pass it as an "
                "argument, e.g. `great import 1001albums <username>`.",
                err=True,
            )
            raise typer.Exit(1)
        data = fetch_project(resolved_username)
        revealed, unrevealed = revealed_counts(data)
        verb = "Would import" if dry_run else "Imported"
        suffix = f" ({unrevealed} more awaiting reveal.)" if unrevealed else ""
        typer.echo(
            f"{verb} {revealed} albums from "
            f"{resolved_username}'s project.{suffix}",
        )
        if dry_run:
            return
        save_project(store.sources_dir, data)
        store.compile()
        if resolved_username != configured:
            store.config.sources[ALBUMSGENERATOR_SOURCE_KEY] = {
                **store.config.sources.get(ALBUMSGENERATOR_SOURCE_KEY, {}),
                "username": resolved_username,
            }
            store.write_config()
            typer.echo(
                f"Saved username to great.toml "
                f"[sources.{ALBUMSGENERATOR_SOURCE_KEY}].",
            )


@import_app.command("antennapod")
def import_antennapod(
    ctx: typer.Context,
    path: Annotated[
        Path,
        typer.Argument(
            help=(
                "Path to an AntennaPod database export "
                "(Settings → Import/Export → Database export)."
            ),
        ),
    ],
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show what would be imported without writing.",
        ),
    ] = False,
) -> None:
    """
    Parse an AntennaPod ``.db`` export and save it as a catalog source.

    The transcoded subset is cached at ``sources/antennapod.json``.
    The derived catalog (read by ranking, render, and ``great show``)
    picks it up on the next read — kept feeds become podcast items,
    played-or-favorited episodes become ``podcast_episode`` items
    parented to their feed, and each played-to-completion episode
    synthesizes a ``consumed`` diary entry.
    """
    with _friendly_errors():
        store = Store.find(ctx.obj)
        data = read_export(path)
        version = data["schema_version"]
        if version != EXPECTED_SCHEMA_VERSION:
            typer.echo(
                f"warning: AntennaPod schema {version} differs from the "
                f"expected {EXPECTED_SCHEMA_VERSION}; some fields may be "
                "missing.",
                err=True,
            )
        podcasts, episodes, completed = antennapod_counts(data)
        verb = "Would import" if dry_run else "Imported"
        typer.echo(
            f"{verb} {podcasts} podcasts and {episodes} episodes "
            f"({completed} played to completion) from {path}.",
        )
        if dry_run:
            return
        save_export(store.sources_dir, data)
        store.compile()

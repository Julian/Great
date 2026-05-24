"""Static-site renderer for a Great data repo."""

from datetime import datetime
from importlib.resources import as_file, files
from itertools import groupby
from pathlib import Path
from typing import Any
from urllib.parse import quote

import jinja2

from great.models import Item, ItemKind, LogEntry
from great.ranking import Score, infer, rescale_to_quantiles
from great.store import MUSIC_KINDS, Store

TIER_LETTERS = ("D", "C", "B", "A", "S")
N_QUANTILES = len(TIER_LETTERS)


def tier_label(quantile: int) -> str:
    """Map a 5-quantile bucket index to a tier letter (D..S)."""
    return TIER_LETTERS[quantile]


def build_site(store: Store, out: Path) -> None:
    """Render the public site for ``store`` into ``out``."""
    out.mkdir(parents=True, exist_ok=True)
    env = jinja2.Environment(
        loader=jinja2.PackageLoader("great", "templates"),
        autoescape=True,
        keep_trailing_newline=True,
    )
    env.filters["slug_href"] = slug_href
    build_ts = datetime.now().astimezone()

    _copy_assets(out)

    all_items = store.all_items()
    items_by_key: dict[tuple[ItemKind, str], Item] = {
        (item.kind, item.id): item for item in all_items
    }
    artist_by_name = {
        i.title: i for i in items_by_key.values() if i.kind == "artist"
    }
    list_data = [
        d for d in _aggregate_lists(store, artist_by_name) if d["ranked"]
    ]
    want_data = _aggregate_wants(store, artist_by_name)
    for queue in want_data:
        for item in queue["ranked"]:
            items_by_key.setdefault((item.kind, item.id), item)
    appears_on_by_name = _appears_on_index(items_by_key)
    log_entries = sorted(store.log(), key=lambda e: e.ts, reverse=True)
    log_view = [
        _log_view(e, items_by_key, artist_by_name) for e in log_entries
    ]

    write = _writer(build_ts)
    write(
        out / "index.html",
        env.get_template("index.html"),
        up="",
        lists=list_data,
        recent_log=[e for e in log_view if e["status"] == "consumed"][:20],
    )

    lists_dir = out / "lists"
    lists_dir.mkdir(exist_ok=True)
    for data in list_data:
        write(
            lists_dir / f"{data['config'].name}.html",
            env.get_template("list.html"),
            up="../",
            list=data,
        )

    item_log: dict[tuple[ItemKind, str], list[LogEntry]] = {}
    for entry in log_entries:
        item_log.setdefault((entry.kind, entry.item), []).append(entry)
    # Per-item pages are gated by configured lists, so importing a kind
    # the user hasn't added to ``great.toml`` (e.g. AntennaPod episodes
    # in a legacy repo) won't suddenly emit thousands of orphan pages.
    # Title resolution above still uses every kind on disk.
    configured_kinds = {lst.kind for lst in store.config.lists}
    for item in items_by_key.values():
        if item.kind not in configured_kinds:
            continue
        in_lists = [
            {
                "config": data["config"],
                "rank": data["ranked"].index(item) + 1,
                "total": len(data["ranked"]),
                "score": data["scores"][item.id],
                "tier": data["tiers"].get(item.id),
            }
            for data in list_data
            if item in data["ranked"]
        ]
        item_path = out / "items" / item.kind / f"{slug(item.id)}.html"
        item_path.parent.mkdir(parents=True, exist_ok=True)
        appears_on = (
            appears_on_by_name.get(item.title, [])
            if item.kind == "artist"
            else []
        )
        write(
            item_path,
            env.get_template("item.html"),
            up="../../",
            item=item,
            creators=_creators_view(
                item.creators,
                artist_by_name,
                up="../../",
            ),
            in_lists=in_lists,
            appears_on=appears_on,
            log_entries=item_log.get((item.kind, item.id), []),
            metadata=item.metadata,
            external_links=_external_links(item.external_ids),
        )

    write(
        out / "diary.html",
        env.get_template("diary.html"),
        up="",
        diary_months=_group_by_month(log_view),
    )

    write(
        out / "queue.html",
        env.get_template("queue.html"),
        up="",
        queues=want_data,
    )


def slug(item_id: str) -> str:
    """
    Map an item id to a filesystem-safe slug for use as a filename.

    Uses percent-encoding (reversible via :func:`urllib.parse.unquote`)
    so that distinct ids never collide. The result contains literal
    ``%`` characters and is NOT safe to drop into a URL directly — use
    :func:`slug_href` for href construction.
    """
    return quote(item_id, safe="")


def slug_href(item_id: str) -> str:
    """
    URL-encoded slug for href attributes.

    The static-site filenames embed literal ``%`` (from :func:`slug`),
    so any href that points at them must encode the ``%`` again. Without
    this, a server receiving ``items/artist/The%20Streets.html`` decodes
    the path once and looks for ``items/artist/The Streets.html`` on
    disk, which doesn't exist.
    """
    return quote(slug(item_id), safe="")


def _log_view(
    entry: LogEntry,
    items_by_key: dict[tuple[ItemKind, str], Item],
    artist_by_name: dict[str, Item],
) -> dict[str, Any]:
    item = items_by_key.get((entry.kind, entry.item))
    creators = item.creators if item else []
    return {
        "ts": entry.ts,
        "status": entry.status,
        "notes": entry.notes,
        "kind": entry.kind,
        "item_id": entry.item,
        "title": item.title if item else entry.item,
        "creators": _creators_view(creators, artist_by_name),
        "href": f"items/{entry.kind}/{slug_href(entry.item)}.html",
    }


def _appears_on_index(
    items_by_key: dict[tuple[ItemKind, str], Item],
) -> dict[str, list[Item]]:
    """
    Build a creator-name → music items index for artist pages.

    Restricted to music kinds: a movie credit happening to share a string
    with an artist's title shouldn't pull the movie onto that artist's page.
    Each list is sorted newest-first, then by title.
    """
    out: dict[str, list[Item]] = {}
    for item in items_by_key.values():
        if item.kind not in MUSIC_KINDS:
            continue
        for name in item.creators:
            out.setdefault(name, []).append(item)
    for credits in out.values():
        credits.sort(key=lambda i: (-(i.year or 0), i.title.casefold()))
    return out


def _creators_view(
    creators: list[str],
    artist_by_name: dict[str, Item],
    *,
    up: str = "",
) -> list[dict[str, str | None]]:
    """Per-creator {name, href} dicts; href is None when no artist exists."""
    out: list[dict[str, str | None]] = []
    for name in creators:
        artist = artist_by_name.get(name)
        href = (
            f"{up}items/artist/{slug_href(artist.id)}.html"
            if artist is not None
            else None
        )
        out.append({"name": name, "href": href})
    return out


def _group_by_month(log_view: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group descending log entries into month buckets, newest first."""
    return [
        {"label": label, "entries": list(entries)}
        for label, entries in groupby(
            log_view,
            key=lambda e: e["ts"].strftime("%B %Y"),
        )
    ]


def rank_by_score(
    items: list[Item],
    scores: dict[str, Score],
) -> list[Item]:
    """Stable score-descending sort with case-insensitive title tiebreak."""
    return sorted(
        items,
        key=lambda i: (-scores[i.id].mean, i.title.casefold()),
    )


def _aggregate_lists(
    store: Store,
    artist_by_name: dict[str, Item],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for list_config in store.config.lists:
        items = store.items(list_config.kind)
        comparisons = store.comparisons(list_config.name)
        scores = infer(comparisons, items)
        # Tiers only make sense once there's actual ranking signal.
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
        ranked = rank_by_score(items, scores)
        out.append(
            {
                "config": list_config,
                "ranked": ranked,
                "scores": scores,
                "tiers": tiers,
                "comparison_count": len(comparisons),
                "rows": _ranked_rows(
                    ranked,
                    scores,
                    tiers,
                    artist_by_name,
                    up="../",
                ),
            },
        )
    return out


def _aggregate_wants(
    store: Store,
    artist_by_name: dict[str, Item],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for kind in sorted({lst.kind for lst in store.config.lists}):
        wants = store.wants(kind)
        if not wants:
            continue
        comparisons = store.want_comparisons(kind)
        scores = infer(comparisons, wants)
        ranked = rank_by_score(wants, scores)
        out.append(
            {
                "kind": kind,
                "ranked": ranked,
                "scores": scores,
                "comparison_count": len(comparisons),
                "rows": _ranked_rows(
                    ranked,
                    scores,
                    {},
                    artist_by_name,
                    up="",
                ),
            },
        )
    return out


def _ranked_rows(
    ranked: list[Item],
    scores: dict[str, Score],
    tiers: dict[str, str],
    artist_by_name: dict[str, Item],
    *,
    up: str,
) -> list[dict[str, Any]]:
    """
    Per-row view data: rank, score, tier, score-bar geometry, tier-break flag.

    The bar is bipolar, centered on 0 and scaled so the largest absolute
    mean fills the row at 100%; ``bar_pct`` is signed (negative grows
    leftward, positive grows rightward in the template).
    """
    scale = max((abs(s.mean) for s in scores.values()), default=0.0) or 1.0
    rows: list[dict[str, Any]] = []
    prev_tier: str | None = None
    for i, item in enumerate(ranked, 1):
        score = scores[item.id]
        tier = tiers.get(item.id)
        rows.append(
            {
                "rank": i,
                "item": item,
                "creators": _creators_view(
                    item.creators,
                    artist_by_name,
                    up=up,
                ),
                "score": score,
                "tier": tier,
                "bar_pct": score.mean / scale * 100.0,
                "tier_break": prev_tier is not None and tier != prev_tier,
            },
        )
        prev_tier = tier
    return rows


def _external_links(
    external_ids: dict[str, str],
) -> list[dict[str, str | None]]:
    """Render external_ids as a list of {source, label, value, url?} dicts."""
    rank = {src: i for i, src in enumerate(EXTERNAL_ID_ORDER)}
    tail = len(EXTERNAL_ID_ORDER)
    ordered = sorted(
        external_ids.items(),
        key=lambda kv: (rank.get(kv[0], tail), kv[0]),
    )
    return [
        {
            "source": source,
            "label": EXTERNAL_ID_LABELS.get(source, source),
            "value": value,
            "url": _external_url(source, value),
        }
        for source, value in ordered
    ]


# Canonical encyclopedia and catalog ids first, then primary streamers,
# then secondary streamers, then importer-specific ids. Unknown sources
# fall to the end in alphabetical order.
EXTERNAL_ID_ORDER: tuple[str, ...] = (
    "wikipedia",
    "musicbrainz_release",
    "musicbrainz_recording",
    "musicbrainz_artist",
    "imdb",
    "tmdb_movie",
    "tmdb_tv",
    "tmdb",
    "openlibrary",
    "isbn",
    "goodreads",
    "igdb",
    "discogs",
    "spotify",
    "apple_music",
    "tidal",
    "deezer",
    "youtube_music",
    "qobuz",
    "bandcamp",
    "1001albums",
)


EXTERNAL_ID_URL_TEMPLATES: dict[str, str] = {
    "imdb": "https://www.imdb.com/title/{}/",
    "tmdb_movie": "https://www.themoviedb.org/movie/{}",
    "tmdb_tv": "https://www.themoviedb.org/tv/{}",
    "isbn": "https://openlibrary.org/isbn/{}",
    "openlibrary": "https://openlibrary.org/works/{}",
    "goodreads": "https://www.goodreads.com/book/show/{}",
    "igdb": "https://www.igdb.com/games/{}",
    "discogs": "https://www.discogs.com/release/{}",
    "wikipedia": "https://en.wikipedia.org/wiki/{}",
    "musicbrainz_release": "https://musicbrainz.org/release/{}",
    "musicbrainz_artist": "https://musicbrainz.org/artist/{}",
    "musicbrainz_recording": "https://musicbrainz.org/recording/{}",
    "apple_music": "https://music.apple.com/album/{}",
    "tidal": "https://tidal.com/browse/album/{}",
    "deezer": "https://www.deezer.com/album/{}",
    "youtube_music": "https://music.youtube.com/playlist?list={}",
}

EXTERNAL_ID_LABELS: dict[str, str] = {
    "imdb": "IMDb",
    "tmdb_movie": "TMDB",
    "tmdb_tv": "TMDB",
    "tmdb": "TMDB",
    "isbn": "ISBN",
    "openlibrary": "Open Library",
    "goodreads": "Goodreads",
    "igdb": "IGDB",
    "discogs": "Discogs",
    "wikipedia": "Wikipedia",
    "musicbrainz_release": "MusicBrainz",
    "musicbrainz_artist": "MusicBrainz",
    "musicbrainz_recording": "MusicBrainz",
    "spotify": "Spotify",
    "apple_music": "Apple Music",
    "tidal": "Tidal",
    "deezer": "Deezer",
    "youtube_music": "YouTube Music",
    "qobuz": "Qobuz",
    "1001albums": "1001 Albums",
    "bandcamp": "Bandcamp",
}


def _external_url(source: str, value: str) -> str | None:
    """Canonical URL for a known external-id source, else None."""
    if source == "spotify" and value.startswith("spotify:"):
        try:
            _, entity, ident = value.split(":", 2)
        except ValueError:
            return None
        return f"https://open.spotify.com/{entity}/{ident}"
    template = EXTERNAL_ID_URL_TEMPLATES.get(source)
    return template.format(value) if template else None


def _copy_assets(out: Path) -> None:
    dst = out / "assets"
    dst.mkdir(exist_ok=True)
    src_root = files("great") / "assets"
    for entry in src_root.iterdir():
        with as_file(entry) as path:
            (dst / entry.name).write_bytes(path.read_bytes())


def _writer(build_ts: datetime) -> Any:
    """Return a writer that injects ``build_ts`` into every render context."""

    def write(
        path: Path,
        template: jinja2.Template,
        **context: object,
    ) -> None:
        path.write_text(template.render(build_ts=build_ts, **context))

    return write

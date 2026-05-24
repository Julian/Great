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
from great.store import Store

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
    env.filters["slug"] = slug
    build_ts = datetime.now().astimezone()

    _copy_assets(out)

    list_data = [d for d in _aggregate_lists(store) if d["ranked"]]
    want_data = _aggregate_wants(store)
    items_by_key: dict[tuple[ItemKind, str], Item] = {
        (item.kind, item.id): item
        for item in [
            *store.all_items(),
            *(item for queue in want_data for item in queue["ranked"]),
        ]
    }
    log_entries = sorted(store.log(), key=lambda e: e.ts, reverse=True)
    log_view = [_log_view(e, items_by_key) for e in log_entries]

    write = _writer(build_ts)
    write(
        out / "index.html",
        env.get_template("index.html"),
        up="",
        lists=list_data,
        recent_log=log_view[:20],
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
    for item in items_by_key.values():
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
        write(
            item_path,
            env.get_template("item.html"),
            up="../../",
            item=item,
            in_lists=in_lists,
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
    Map an item id to a filesystem- and URL-safe slug.

    Uses percent-encoding (reversible via :func:`urllib.parse.unquote`)
    so that distinct ids never collide.
    """
    return quote(item_id, safe="")


def _log_view(
    entry: LogEntry,
    items_by_key: dict[tuple[ItemKind, str], Item],
) -> dict[str, Any]:
    item = items_by_key.get((entry.kind, entry.item))
    return {
        "ts": entry.ts,
        "status": entry.status,
        "notes": entry.notes,
        "kind": entry.kind,
        "item_id": entry.item,
        "title": item.title if item else entry.item,
        "creators": item.creators if item else [],
        "href": f"items/{entry.kind}/{slug(entry.item)}.html",
    }


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


def _aggregate_lists(store: Store) -> list[dict[str, Any]]:
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
                "rows": _ranked_rows(ranked, scores, tiers),
            },
        )
    return out


def _aggregate_wants(store: Store) -> list[dict[str, Any]]:
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
                "rows": _ranked_rows(ranked, scores, tiers={}),
            },
        )
    return out


def _ranked_rows(
    ranked: list[Item],
    scores: dict[str, Score],
    tiers: dict[str, str],
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
    return [
        {
            "source": source,
            "label": EXTERNAL_ID_LABELS.get(source, source),
            "value": value,
            "url": _external_url(source, value),
        }
        for source, value in external_ids.items()
    ]


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

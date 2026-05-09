"""Static-site renderer for a Great data repo."""

from importlib.resources import as_file, files
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import jinja2

from great.ranking import infer, rescale_to_quantiles
from great.store import Store

if TYPE_CHECKING:
    from great.models import LogEntry

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

    _copy_assets(out)

    list_data = _aggregate_lists(store)
    items_by_id = {item.id: item for item in store.all_items()}
    log_entries = sorted(store.log(), key=lambda e: e.ts, reverse=True)

    _write(
        out / "index.html",
        env.get_template("index.html"),
        up="",
        lists=list_data,
        recent_log=log_entries[:20],
        item_index=items_by_id,
    )

    lists_dir = out / "lists"
    lists_dir.mkdir(exist_ok=True)
    for data in list_data:
        _write(
            lists_dir / f"{data['config'].name}.html",
            env.get_template("list.html"),
            up="../",
            list=data,
        )

    items_dir = out / "items"
    items_dir.mkdir(exist_ok=True)
    item_log: dict[str, list[LogEntry]] = {}
    for entry in log_entries:
        item_log.setdefault(entry.item, []).append(entry)
    for item in items_by_id.values():
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
        _write(
            items_dir / f"{slug(item.id)}.html",
            env.get_template("item.html"),
            up="../",
            item=item,
            in_lists=in_lists,
            log_entries=item_log.get(item.id, []),
            metadata=item.metadata,
        )

    _write(
        out / "diary.html",
        env.get_template("diary.html"),
        up="",
        log_entries=log_entries,
        item_index=items_by_id,
    )

    _write(
        out / "queue.html",
        env.get_template("queue.html"),
        up="",
        lists=list_data,
        item_index=items_by_id,
    )


def slug(item_id: str) -> str:
    """
    Map an item id to a filesystem- and URL-safe slug.

    Uses percent-encoding (reversible via :func:`urllib.parse.unquote`)
    so that distinct ids never collide.
    """
    return quote(item_id, safe="")


def _aggregate_lists(store: Store) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for list_config in store.config.lists:
        items = store.items(list_config.kind)
        comparisons = store.comparisons(list_config.name)
        scores = infer(comparisons, items)
        ranked = sorted(items, key=lambda i: scores[i.id].mean, reverse=True)
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
        out.append(
            {
                "config": list_config,
                "ranked": ranked,
                "scores": scores,
                "tiers": tiers,
                "comparison_count": len(comparisons),
                "wants": store.wants(list_config.name),
            },
        )
    return out


def _copy_assets(out: Path) -> None:
    dst = out / "assets"
    dst.mkdir(exist_ok=True)
    src_root = files("great") / "assets"
    for entry in src_root.iterdir():
        with as_file(entry) as path:
            (dst / entry.name).write_bytes(path.read_bytes())


def _write(
    path: Path,
    template: jinja2.Template,
    **context: object,
) -> None:
    path.write_text(template.render(**context))

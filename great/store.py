"""
Read and write a Great data repo.

A data repo is a directory containing ``great.toml`` plus four
sibling subdirectories: ``items/``, ``comparisons/``, ``log/``, and
``want/``. Items (consumed and wanted alike) live in TOML; comparisons
and log entries are append-only JSONL. The want queue uses the same
``Item`` schema as the consumed catalog and is kept disjoint from it.
"""

from pathlib import Path
from typing import Any
import tomllib

from pydantic import BaseModel
import tomli_w

from great.models import (
    KIND_PLURAL,
    Comparison,
    GreatConfig,
    Item,
    ItemKind,
    ListConfig,
    LogEntry,
)

CONFIG_FILE = "great.toml"


def items_file(kind: ItemKind) -> str:
    """Repo-relative path of the consumed-items TOML for ``kind``."""
    return f"items/{KIND_PLURAL[kind]}.toml"


def want_file(kind: ItemKind) -> str:
    """Repo-relative path of the want-queue TOML for ``kind``."""
    return f"want/{KIND_PLURAL[kind]}.toml"


class StoreError(Exception):
    """A storage error."""


class StoreNotFoundError(StoreError):
    """No ``great.toml`` was found walking up from the start path."""


class ListNotFoundError(StoreError):
    """A referenced list name is not declared in the config."""


class CorruptStoreError(StoreError):
    """An on-disk data file violates an invariant."""


class Store:
    """Read/write a Great data repo rooted at ``root``."""

    def __init__(self, root: Path):
        self.root = root
        with (root / CONFIG_FILE).open("rb") as f:
            self.config = GreatConfig.model_validate(tomllib.load(f))

    @classmethod
    def find(cls, start: Path | None = None) -> "Store":
        """Walk upward from ``start`` (or cwd) until a config is found."""
        path = (start or Path.cwd()).resolve()
        for candidate in [path, *path.parents]:
            if (candidate / CONFIG_FILE).is_file():
                return cls(candidate)
        raise StoreNotFoundError(
            f"no {CONFIG_FILE} found in {path} or any parent",
        )

    @classmethod
    def init(cls, root: Path, config: GreatConfig) -> "Store":
        """Initialize an empty data repo at ``root``."""
        root.mkdir(parents=True, exist_ok=True)
        for sub in ("items", "comparisons/want", "log", "want"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        with (root / CONFIG_FILE).open("wb") as f:
            tomli_w.dump(_dump(config), f)
        return cls(root)

    def list_config(self, name: str) -> ListConfig:
        """Return the configured list with the given name."""
        for lst in self.config.lists:
            if lst.name == name:
                return lst
        raise ListNotFoundError(f"unknown list: {name!r}")

    def items(self, kind: ItemKind) -> list[Item]:
        """Return consumed items of the given kind (catalog only)."""
        return self._read_items(self._items_path(kind), kind)

    def all_items(self) -> list[Item]:
        """Return consumed items across all kinds."""
        return [
            item
            for kind in sorted({lst.kind for lst in self.config.lists})
            for item in self.items(kind)
        ]

    def write_items(self, kind: ItemKind, items: list[Item]) -> None:
        """Replace the consumed-items file for ``kind`` with ``items``."""
        self._write_items(self._items_path(kind), kind, items)

    def add_item(self, item: Item) -> bool:
        """
        Append ``item`` to its kind's consumed catalog.

        Returns ``True`` if newly added, ``False`` if already present.
        Raises ``StoreError`` if the id is already on the want queue --
        the catalog and want queue are kept disjoint.
        """
        if any(w.id == item.id for w in self.wants(item.kind)):
            raise StoreError(
                f"{item.id!r} is already in {want_file(item.kind)}; "
                "won't add to the consumed catalog.",
            )
        items = self.items(item.kind)
        if any(i.id == item.id for i in items):
            return False
        items.append(item)
        self.write_items(item.kind, items)
        return True

    def wants(self, kind: ItemKind) -> list[Item]:
        """Return want-queue items for ``kind`` (per kind, single queue)."""
        return self._read_items(self._wants_path(kind), kind)

    def write_wants(self, kind: ItemKind, items: list[Item]) -> None:
        """Replace the want queue for ``kind`` with ``items``."""
        self._write_items(self._wants_path(kind), kind, items)

    def add_want(self, item: Item) -> bool:
        """
        Append ``item`` to its kind's want queue.

        Returns ``True`` if newly added, ``False`` if already present.
        Raises ``StoreError`` if the id is already in the consumed
        catalog — the catalog and want queue are kept disjoint.
        """
        if any(i.id == item.id for i in self.items(item.kind)):
            raise StoreError(
                f"{item.id!r} is already in {items_file(item.kind)}; "
                "won't add to the want queue.",
            )
        wants = self.wants(item.kind)
        if any(w.id == item.id for w in wants):
            return False
        wants.append(item)
        self.write_wants(item.kind, wants)
        return True

    def remove_want(self, kind: ItemKind, item_id: str) -> bool:
        """Remove ``item_id`` from ``kind``'s want queue; return if removed."""
        wants = self.wants(kind)
        kept = [w for w in wants if w.id != item_id]
        if len(kept) == len(wants):
            return False
        self.write_wants(kind, kept)
        return True

    def promote_want(self, kind: ItemKind, item_id: str) -> Item | None:
        """
        Move ``item_id`` from the want queue into the consumed catalog.

        Returns the promoted item, or ``None`` if not on the want queue.
        Catalog uniqueness is preserved: if the id already exists in
        ``items/<kind>.toml`` the want entry is dropped without
        duplicating. The catalog write happens before the want
        removal so an interrupted run leaves a recoverable duplicate
        rather than a lost record.
        """
        wants = self.wants(kind)
        promoted = next((w for w in wants if w.id == item_id), None)
        if promoted is None:
            return None
        items = self.items(kind)
        if not any(i.id == item_id for i in items):
            items.append(promoted)
            self.write_items(kind, items)
        self.write_wants(kind, [w for w in wants if w.id != item_id])
        return promoted

    def comparisons(self, list_name: str) -> list[Comparison]:
        """Return all favorite-ranking comparisons for ``list_name``."""
        return self._read_comparisons(self._comparisons_path(list_name))

    def append_comparison(self, list_name: str, c: Comparison) -> None:
        """Append a favorite-ranking comparison to ``list_name``'s log."""
        _append_jsonl(
            self._comparisons_path(list_name),
            c.model_dump_json(exclude_none=True),
        )

    def want_comparisons(self, kind: ItemKind) -> list[Comparison]:
        """Return all want-ranking comparisons for ``kind``."""
        return self._read_comparisons(self._want_comparisons_path(kind))

    def append_want_comparison(self, kind: ItemKind, c: Comparison) -> None:
        """Append a want-ranking comparison to ``kind``'s want log."""
        _append_jsonl(
            self._want_comparisons_path(kind),
            c.model_dump_json(exclude_none=True),
        )

    def log(self, year: int | None = None) -> list[LogEntry]:
        """Return diary entries (optionally filtered to a single year)."""
        log_dir = self.root / "log"
        if not log_dir.is_dir():
            return []
        files = sorted(log_dir.glob("*.jsonl"))
        if year is not None:
            files = [f for f in files if f.stem == str(year)]
        return [
            LogEntry.model_validate_json(line)
            for path in files
            for line in _read_jsonl(path)
        ]

    def append_log(self, entry: LogEntry) -> None:
        """Append a diary entry to the log for its year."""
        path = self.root / "log" / f"{entry.ts.year}.jsonl"
        _append_jsonl(path, entry.model_dump_json(exclude_none=True))

    def _items_path(self, kind: ItemKind) -> Path:
        return self.root / items_file(kind)

    def _wants_path(self, kind: ItemKind) -> Path:
        return self.root / want_file(kind)

    def _comparisons_path(self, list_name: str) -> Path:
        return self.root / "comparisons" / f"{list_name}.jsonl"

    def _want_comparisons_path(self, kind: ItemKind) -> Path:
        return (
            self.root / "comparisons" / "want" / f"{KIND_PLURAL[kind]}.jsonl"
        )

    def _read_items(self, path: Path, kind: ItemKind) -> list[Item]:
        if not path.is_file():
            return []
        with path.open("rb") as f:
            data = tomllib.load(f)
        items: list[Item] = []
        seen: set[str] = set()
        for raw in data.get("items", []):
            try:
                item = Item.from_dict(raw, kind=kind)
            except ValueError as e:
                raise CorruptStoreError(f"{path}: {e}") from e
            if item.id in seen:
                raise CorruptStoreError(
                    f"{path}: duplicate item id {item.id!r}",
                )
            seen.add(item.id)
            items.append(item)
        return items

    def _write_items(
        self,
        path: Path,
        kind: ItemKind,
        items: list[Item],
    ) -> None:
        for item in items:
            if item.kind != kind:
                raise ValueError(
                    f"item {item.id!r} has kind {item.kind!r}, "
                    f"cannot write to {path}",
                )
        if not items:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"items": [i.to_dict() for i in items]}
        with path.open("wb") as f:
            tomli_w.dump(payload, f)

    def _read_comparisons(self, path: Path) -> list[Comparison]:
        return [
            Comparison.model_validate_json(line) for line in _read_jsonl(path)
        ]


def _dump(model: BaseModel) -> dict[str, Any]:
    """Dump a pydantic model to a TOML-friendly dict."""
    return model.model_dump(
        mode="python",
        exclude_defaults=True,
        exclude_none=True,
    )


def _read_jsonl(path: Path) -> list[str]:
    """Return the non-empty lines of a JSONL file (or [] if missing)."""
    if not path.is_file():
        return []
    with path.open() as f:
        return [line for line in f if line.strip()]


def _append_jsonl(path: Path, line: str) -> None:
    """Append a single JSON line to ``path``, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(line + "\n")

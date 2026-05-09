"""
Read and write a Great data repo.

A data repo is a directory containing ``great.toml`` plus four
sibling subdirectories: ``items/``, ``comparisons/``, ``log/``, and
``want/``. Items and want-entries live in TOML; comparisons and log
entries are append-only JSONL.
"""

from pathlib import Path
from typing import Any
import tomllib

from pydantic import BaseModel
import tomli_w

from great.models import (
    Comparison,
    GreatConfig,
    Item,
    ItemKind,
    ListConfig,
    LogEntry,
    WantEntry,
)

CONFIG_FILE = "great.toml"


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
        for sub in ("", "items", "comparisons", "log", "want"):
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
        """Return all items of the given kind, validating invariants."""
        path = self.root / "items" / f"{kind}.toml"
        if not path.is_file():
            return []
        with path.open("rb") as f:
            data = tomllib.load(f)
        items = [Item.model_validate(i) for i in data.get("items", [])]
        seen: set[str] = set()
        for item in items:
            if item.kind != kind:
                raise CorruptStoreError(
                    f"{path}: item {item.id!r} has kind {item.kind!r}, "
                    f"expected {kind!r}",
                )
            if item.id in seen:
                raise CorruptStoreError(
                    f"{path}: duplicate item id {item.id!r}",
                )
            seen.add(item.id)
        return items

    def all_items(self) -> list[Item]:
        """
        Return items across all configured kinds, globally id-unique.

        Raises :class:`CorruptStoreError` if the same id appears in two
        different kinds.
        """
        out: list[Item] = []
        seen: dict[str, ItemKind] = {}
        for kind in sorted({lst.kind for lst in self.config.lists}):
            for item in self.items(kind):
                if item.id in seen and seen[item.id] != item.kind:
                    raise CorruptStoreError(
                        f"item id {item.id!r} appears in both "
                        f"{seen[item.id]!r} and {item.kind!r} kinds; "
                        "ids must be globally unique",
                    )
                seen[item.id] = item.kind
                out.append(item)
        return out

    def write_items(self, kind: ItemKind, items: list[Item]) -> None:
        """Replace the items file for ``kind`` with ``items``."""
        path = self.root / "items" / f"{kind}.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"items": [_dump(i) for i in items]}
        with path.open("wb") as f:
            tomli_w.dump(payload, f)

    def comparisons(self, list_name: str) -> list[Comparison]:
        """Return all comparisons recorded for ``list_name``."""
        path = self.root / "comparisons" / f"{list_name}.jsonl"
        return [
            Comparison.model_validate_json(line) for line in _read_jsonl(path)
        ]

    def append_comparison(self, c: Comparison) -> None:
        """Append a comparison to the list's JSONL log."""
        path = self.root / "comparisons" / f"{c.list}.jsonl"
        _append_jsonl(path, c.model_dump_json(exclude_none=True))

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

    def wants(self, list_name: str) -> list[WantEntry]:
        """Return want-to-consume entries for ``list_name``."""
        path = self.root / "want" / f"{list_name}.toml"
        if not path.is_file():
            return []
        with path.open("rb") as f:
            data = tomllib.load(f)
        return [WantEntry.model_validate(w) for w in data.get("wants", [])]

    def add_want(self, list_name: str, want: WantEntry) -> None:
        """Append a want-entry, rewriting the list's TOML file."""
        existing = self.wants(list_name)
        existing.append(want)
        self._write_wants(list_name, existing)

    def remove_want(self, list_name: str, item_id: str) -> bool:
        """Remove ``item_id`` from ``list_name``; return whether it existed."""
        wants = self.wants(list_name)
        kept = [w for w in wants if w.item != item_id]
        if len(kept) == len(wants):
            return False
        self._write_wants(list_name, kept)
        return True

    def discard_from_wants(self, item_id: str) -> int:
        """Remove ``item_id`` from every want list; return how many removed."""
        want_dir = self.root / "want"
        if not want_dir.is_dir():
            return 0
        return sum(
            1
            for path in want_dir.glob("*.toml")
            if self.remove_want(path.stem, item_id)
        )

    def _write_wants(
        self,
        list_name: str,
        wants: list[WantEntry],
    ) -> None:
        path = self.root / "want" / f"{list_name}.toml"
        if not wants:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"wants": [_dump(w) for w in wants]}
        with path.open("wb") as f:
            tomli_w.dump(payload, f)


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

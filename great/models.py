"""
Data model for items, comparisons, log entries, want entries, and config.

These are the shapes serialized to and from a Great data repo. TOML for
items / want entries / config; JSONL for the append-only comparison and
log streams.
"""

from datetime import date, datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

ItemKind = Literal["movie", "tv", "song", "album", "podcast", "book"]
LogStatus = Literal["consumed", "started", "abandoned"]
Priority = Literal["low", "normal", "high"]


class Item(BaseModel):
    """
    A single rankable item.

    `id` is a canonical external id (IMDB ``tt12345``, MusicBrainz UUID,
    Spotify URI, etc.) and must be globally unique across all kinds —
    log entries, want entries, and comparisons reference items by
    ``id`` alone, so cross-kind collisions break those references.
    Real-world canonical ids satisfy this naturally.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: ItemKind
    title: str
    year: int | None = None
    external_ids: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, kind: ItemKind) -> Self:
        """Build an Item from a TOML mapping; the file's kind is supplied."""
        if "kind" in data:
            raise ValueError(
                "item must not declare `kind` (it's implied by the items "
                "file it lives in)",
            )
        return cls.model_validate({**data, "kind": kind})

    def to_dict(self) -> dict[str, Any]:
        """Dump for storage; ``kind`` is omitted (lives in the filename)."""
        return self.model_dump(
            mode="python",
            exclude={"kind"},
            exclude_defaults=True,
            exclude_none=True,
        )


class Comparison(BaseModel):
    """
    A single ranking judgment over 2..k items.

    ``ordering`` is a list of tie groups, best to worst. Each group is
    a list of indices into ``items`` that the user judged
    indistinguishable from one another. A fully-ordered comparison has
    one item per group (e.g. ``[[0], [1], [2]]``); an all-tied
    comparison has a single group (e.g. ``[[0, 1, 2]]``); partial
    ties are also expressible (e.g. ``[[2], [0, 1]]``).
    """

    model_config = ConfigDict(extra="forbid")

    ts: datetime
    list: str
    items: list[str] = Field(min_length=2)
    ordering: list[list[int]] = Field(min_length=1)

    @model_validator(mode="after")
    def _ordering_partitions_items(self) -> Self:
        flat = sorted(i for group in self.ordering for i in group)
        if any(not group for group in self.ordering):
            raise ValueError("tie groups must be non-empty")
        if flat != list(range(len(self.items))):
            raise ValueError(
                "ordering must partition the indices of `items`",
            )
        return self


class LogEntry(BaseModel):
    """A consumption diary entry."""

    model_config = ConfigDict(extra="forbid")

    ts: datetime
    item: str
    status: LogStatus
    notes: str | None = None


class WantEntry(BaseModel):
    """A want-to-consume queue entry."""

    model_config = ConfigDict(extra="forbid")

    item: str
    added: date
    priority: Priority = "normal"


class ListConfig(BaseModel):
    """Configuration for a single list (e.g. ``movies``)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: ItemKind
    description: str | None = None


class GreatConfig(BaseModel):
    """The top-level configuration in ``great.toml``."""

    model_config = ConfigDict(extra="forbid")

    lists: list[ListConfig] = Field(default_factory=list)
    theme: str = "default"
    sources: dict[str, dict[str, str]] = Field(default_factory=dict)

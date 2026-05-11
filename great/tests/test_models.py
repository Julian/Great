from datetime import UTC, datetime

from pydantic import ValidationError
import pytest

from great.models import (
    Comparison,
    GreatConfig,
    Item,
    ListConfig,
    LogEntry,
)


def test_item_minimal():
    item = Item(id="tt1", kind="movie", title="Anora")
    assert item.year is None
    assert item.external_ids == {}
    assert item.metadata == {}


def test_item_round_trip():
    item = Item(
        id="tt1",
        kind="movie",
        title="Anora",
        year=2024,
        external_ids={"imdb": "tt1"},
        metadata={"director": "Sean Baker"},
    )
    assert Item.model_validate(item.model_dump()) == item


def test_item_rejects_unknown_field():
    with pytest.raises(ValidationError):
        Item.model_validate(
            {"id": "tt1", "kind": "movie", "title": "x", "bogus": 1},
        )


def test_item_rejects_bad_kind():
    with pytest.raises(ValidationError):
        Item.model_validate({"id": "x", "kind": "potato", "title": "x"})


def test_item_id_defaults_to_title():
    item = Item.model_validate({"kind": "movie", "title": "Anora"})
    assert item.id == "Anora"


def test_item_explicit_id_wins_over_title():
    item = Item.model_validate(
        {"id": "tt1", "kind": "movie", "title": "Anora"},
    )
    assert item.id == "tt1"


def test_item_round_trip_preserves_defaulted_id():
    item = Item.model_validate({"kind": "movie", "title": "Anora"})
    dumped = item.model_dump(exclude={"kind"}, exclude_defaults=True)
    assert dumped["id"] == "Anora"


def test_comparison_pairwise():
    c = Comparison(
        ts=datetime(2026, 5, 9, 14, 0, tzinfo=UTC),
        items=["a", "b"],
        ordering=[[0], [1]],
    )
    assert c.ordering == [[0], [1]]


def test_comparison_kway():
    c = Comparison(
        ts=datetime(2026, 5, 9, tzinfo=UTC),
        items=["a", "b", "c"],
        ordering=[[2], [0], [1]],
    )
    assert c.items == ["a", "b", "c"]
    assert c.ordering == [[2], [0], [1]]


def test_comparison_tie():
    c = Comparison(
        ts=datetime(2026, 5, 9, tzinfo=UTC),
        items=["a", "b"],
        ordering=[[0, 1]],
    )
    assert c.ordering == [[0, 1]]


def test_comparison_partial_tie():
    c = Comparison(
        ts=datetime(2026, 5, 9, tzinfo=UTC),
        items=["a", "b", "c"],
        ordering=[[2], [0, 1]],
    )
    assert c.ordering == [[2], [0, 1]]


def test_comparison_requires_two_items():
    with pytest.raises(ValidationError):
        Comparison(
            ts=datetime(2026, 5, 9, tzinfo=UTC),
            items=["only-one"],
            ordering=[[0]],
        )


def test_comparison_rejects_non_partition():
    with pytest.raises(ValidationError, match="partition"):
        Comparison(
            ts=datetime(2026, 5, 9, tzinfo=UTC),
            items=["a", "b"],
            ordering=[[0], [0]],
        )


def test_comparison_rejects_empty_group():
    with pytest.raises(ValidationError, match="non-empty"):
        Comparison(
            ts=datetime(2026, 5, 9, tzinfo=UTC),
            items=["a", "b"],
            ordering=[[0, 1], []],
        )


def test_log_entry_minimal():
    entry = LogEntry(
        ts=datetime(2026, 5, 9, tzinfo=UTC),
        kind="movie",
        item="tt1",
        status="consumed",
    )
    assert entry.notes is None
    assert entry.kind == "movie"


def test_great_config_defaults():
    config = GreatConfig()
    assert config.theme == "default"
    assert config.lists == []


def test_list_config():
    lst = ListConfig(name="movies", kind="movie")
    assert lst.description is None

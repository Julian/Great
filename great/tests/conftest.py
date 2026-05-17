"""Shared pytest fixtures for the test suite."""

import pytest

from great.models import GreatConfig, Item, ListConfig
from great.store import Store


@pytest.fixture
def make_movies_store():
    """
    Factory that initializes a movies-only data repo at a given path.

    Defaults to two items (Anora, Casablanca) so the store can already
    be ranked; pass ``items=[...]`` to override.
    """

    def _make(path, *, items=None):
        config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
        store = Store.init(path, config)
        if items is None:
            items = [
                Item(id="tt1", kind="movie", title="Anora", year=2024),
                Item(id="tt2", kind="movie", title="Casablanca", year=1942),
            ]
        store.write_items("movie", items)
        return store

    return _make

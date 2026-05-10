from datetime import UTC, date, datetime

import pytest

from great.models import (
    Comparison,
    GreatConfig,
    Item,
    ListConfig,
    LogEntry,
    WantEntry,
)
from great.render import build_site, slug
from great.store import Store


@pytest.fixture
def populated(tmp_path):
    config = GreatConfig(
        lists=[
            ListConfig(name="movies", kind="movie", description="Films"),
            ListConfig(name="tv", kind="tv"),
        ],
    )
    store = Store.init(tmp_path, config)
    store.write_items(
        "movie",
        [
            Item(id="tt1", kind="movie", title="Anora", year=2024),
            Item(id="tt2", kind="movie", title="Casablanca", year=1942),
        ],
    )
    store.write_items(
        "tv",
        [Item(id="tv1", kind="tv", title="Severance", year=2022)],
    )
    store.append_comparison(
        Comparison(
            ts=datetime(2026, 5, 9, tzinfo=UTC),
            list="movies",
            items=["tt1", "tt2"],
            ordering=[[0], [1]],
        ),
    )
    store.append_log(
        LogEntry(
            ts=datetime(2026, 5, 9, tzinfo=UTC),
            kind="movie",
            item="tt1",
            status="consumed",
            notes="loved it",
        ),
    )
    store.add_want(
        "tv",
        WantEntry(item="tv1", added=date(2026, 5, 9), priority="high"),
    )
    return store


def test_slug_keeps_unreserved_chars():
    assert slug("tt12345") == "tt12345"
    assert slug("hello.world-1") == "hello.world-1"
    assert slug("hello_world~1") == "hello_world~1"


def test_slug_percent_encodes_unsafe_chars():
    assert slug("spotify:track:abc/def") == "spotify%3Atrack%3Aabc%2Fdef"


def test_slug_avoids_collisions():
    assert slug("a:b") != slug("a_b")
    assert slug("a/b") != slug("a-b")


def test_build_creates_expected_files(populated, tmp_path):
    out = tmp_path / "dist"
    build_site(populated, out)
    assert (out / "index.html").is_file()
    assert (out / "diary.html").is_file()
    assert (out / "queue.html").is_file()
    assert (out / "lists" / "movies.html").is_file()
    assert (out / "lists" / "tv.html").is_file()
    assert (out / "items" / "movie" / "tt1.html").is_file()
    assert (out / "items" / "movie" / "tt2.html").is_file()
    assert (out / "items" / "tv" / "tv1.html").is_file()
    assert (out / "assets" / "style.css").is_file()


def test_list_page_shows_inferred_ranking(populated, tmp_path):
    out = tmp_path / "dist"
    build_site(populated, out)
    html = (out / "lists" / "movies.html").read_text()
    anora_pos = html.find("Anora")
    casa_pos = html.find("Casablanca")
    assert 0 < anora_pos < casa_pos  # Anora is ranked higher


def test_index_lists_recent_log(populated, tmp_path):
    out = tmp_path / "dist"
    build_site(populated, out)
    html = (out / "index.html").read_text()
    assert "Anora" in html
    assert "consumed" in html


def test_diary_shows_notes(populated, tmp_path):
    out = tmp_path / "dist"
    build_site(populated, out)
    html = (out / "diary.html").read_text()
    assert "loved it" in html
    assert "Anora" in html


def test_queue_shows_wants(populated, tmp_path):
    out = tmp_path / "dist"
    build_site(populated, out)
    html = (out / "queue.html").read_text()
    assert "Severance" in html
    assert "high" in html
    assert "Nothing in the queue" not in html


def test_queue_empty_state_when_no_wants(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    store = Store.init(tmp_path, config)
    out = tmp_path / "dist"
    build_site(store, out)
    html = (out / "queue.html").read_text()
    assert "Nothing in the queue" in html


def test_item_page_shows_metadata_and_diary(populated, tmp_path):
    out = tmp_path / "dist"
    build_site(populated, out)
    html = (out / "items" / "movie" / "tt1.html").read_text()
    assert "Anora" in html
    assert "tt1" in html
    assert "loved it" in html


def test_empty_store_renders_without_error(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    store = Store.init(tmp_path, config)
    out = tmp_path / "dist"
    build_site(store, out)
    assert (out / "index.html").is_file()
    assert (out / "lists" / "movies.html").is_file()


def test_list_page_shows_tier_when_comparisons_exist(populated, tmp_path):
    out = tmp_path / "dist"
    build_site(populated, out)
    html = (out / "lists" / "movies.html").read_text()
    assert "Tier" in html
    assert 'class="tier' in html


def test_cross_kind_same_id_produces_separate_item_pages(tmp_path):
    config = GreatConfig(
        lists=[
            ListConfig(name="movies", kind="movie"),
            ListConfig(name="books", kind="book"),
        ],
    )
    store = Store.init(tmp_path, config)
    store.write_items(
        "movie",
        [Item(id="Dune", kind="movie", title="Dune", year=2021)],
    )
    store.write_items(
        "book",
        [Item(id="Dune", kind="book", title="Dune", year=1965)],
    )
    out = tmp_path / "dist"
    build_site(store, out)
    movie_page = (out / "items" / "movie" / "Dune.html").read_text()
    book_page = (out / "items" / "book" / "Dune.html").read_text()
    assert "2021" in movie_page
    assert "2021" not in book_page
    assert "1965" in book_page


def test_list_page_omits_tier_without_comparisons(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    store = Store.init(tmp_path, config)
    store.write_items(
        "movie",
        [
            Item(id="tt1", kind="movie", title="Anora"),
            Item(id="tt2", kind="movie", title="Casablanca"),
        ],
    )
    out = tmp_path / "dist"
    build_site(store, out)
    html = (out / "lists" / "movies.html").read_text()
    assert "<th>Tier</th>" not in html

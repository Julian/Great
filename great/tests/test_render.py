from datetime import UTC, datetime
from pathlib import Path

import pytest

from great.models import (
    Comparison,
    GreatConfig,
    Item,
    ListConfig,
    LogEntry,
)
from great.render import build_site, slug, slug_href
from great.store import Store

SAMPLE_DATA = Path(__file__).parents[2] / "examples" / "sample-data"


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
        "movies",
        Comparison(
            ts=datetime(2026, 5, 9, tzinfo=UTC),
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
    store.add_want(Item(id="The Bear", kind="tv", title="The Bear", year=2022))
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


def test_slug_href_double_encodes_so_url_resolves_to_filename():
    # The filename literally contains '%', so the href must encode it
    # again — when a static server URL-decodes the request path once,
    # it has to land back on the on-disk name.
    from urllib.parse import unquote  # noqa: PLC0415

    for raw in ["The Streets", "spotify:track:abc/def", "Don't"]:
        assert unquote(slug_href(raw)) == slug(raw)


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
    # The "Recently consumed" section title already says it; we don't
    # want a status-consumed badge repeated on every row.
    assert "Recently consumed" in html
    assert "status-consumed" not in html


def test_diary_still_shows_status_badges(populated, tmp_path):
    # Diary is a full activity log, not filtered to consumed, so the
    # per-entry status badge stays.
    out = tmp_path / "dist"
    build_site(populated, out)
    html = (out / "diary.html").read_text()
    assert "status-consumed" in html


def test_index_and_diary_link_creator_to_artist_page(tmp_path):
    config = GreatConfig(
        lists=[
            ListConfig(name="albums", kind="album"),
            ListConfig(name="artists", kind="artist"),
        ],
    )
    store = Store.init(tmp_path, config)
    store.write_items(
        "album",
        [
            Item(
                id="spotify:album:1",
                kind="album",
                title="Crazysexycool",
                creators=["TLC"],
            ),
        ],
    )
    store.append_log(
        LogEntry(
            ts=datetime(2026, 5, 1, tzinfo=UTC),
            kind="album",
            item="spotify:album:1",
            status="consumed",
        ),
    )
    out = tmp_path / "dist"
    build_site(store, out)
    index = (out / "index.html").read_text()
    diary = (out / "diary.html").read_text()
    # The auto-synthesized TLC artist gets linked from both views.
    expected = '<a href="items/artist/TLC.html">TLC</a>'
    assert expected in index
    assert expected in diary


def test_item_page_links_creator_to_artist_page(tmp_path):
    config = GreatConfig(
        lists=[
            ListConfig(name="albums", kind="album"),
            ListConfig(name="artists", kind="artist"),
        ],
    )
    store = Store.init(tmp_path, config)
    store.write_items(
        "album",
        [
            Item(
                id="spotify:album:1",
                kind="album",
                title="Crazysexycool",
                creators=["TLC"],
            ),
        ],
    )
    out = tmp_path / "dist"
    build_site(store, out)
    page = (out / "items" / "album" / "spotify%3Aalbum%3A1.html").read_text()
    assert '<a href="../../items/artist/TLC.html">TLC</a>' in page


def test_index_recent_log_only_shows_consumed(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    store = Store.init(tmp_path, config)
    store.write_items(
        "movie",
        [Item(id="tt1", kind="movie", title="Anora", year=2024)],
    )
    # An abandoned entry should not surface in "Recently consumed",
    # but should still appear in the full diary.
    store.append_log(
        LogEntry(
            ts=datetime(2026, 5, 1, tzinfo=UTC),
            kind="movie",
            item="tt1",
            status="abandoned",
        ),
    )
    out = tmp_path / "dist"
    build_site(store, out)
    assert "Anora" not in (out / "index.html").read_text()
    assert "Anora" in (out / "diary.html").read_text()


def test_artist_page_lists_appears_on(tmp_path):
    config = GreatConfig(
        lists=[
            ListConfig(name="albums", kind="album"),
            ListConfig(name="artists", kind="artist"),
        ],
    )
    store = Store.init(tmp_path, config)
    store.write_items(
        "album",
        [
            Item(
                id="a1",
                kind="album",
                title="Crazysexycool",
                year=1994,
                creators=["TLC"],
            ),
            Item(
                id="a2",
                kind="album",
                title="Fanmail",
                year=1999,
                creators=["TLC"],
            ),
            Item(
                id="a3",
                kind="album",
                title="Unrelated",
                creators=["Other"],
            ),
        ],
    )
    out = tmp_path / "dist"
    build_site(store, out)
    page = (out / "items" / "artist" / "TLC.html").read_text()
    assert "Appears on" in page
    assert "Crazysexycool" in page
    assert "Fanmail" in page
    assert "Unrelated" not in page
    # Newest first.
    assert page.find("Fanmail") < page.find("Crazysexycool")


def test_appears_on_excludes_non_music_items(tmp_path):
    # A movie sharing a creator-name string with an artist title should
    # not be pulled onto the artist's page.
    config = GreatConfig(
        lists=[
            ListConfig(name="movies", kind="movie"),
            ListConfig(name="albums", kind="album"),
            ListConfig(name="artists", kind="artist"),
        ],
    )
    store = Store.init(tmp_path, config)
    store.write_items(
        "movie",
        [Item(id="m1", kind="movie", title="Movie", creators=["TLC"])],
    )
    store.write_items(
        "album",
        [Item(id="a1", kind="album", title="Album", creators=["TLC"])],
    )
    out = tmp_path / "dist"
    build_site(store, out)
    page = (out / "items" / "artist" / "TLC.html").read_text()
    assert "Album" in page
    assert "Movie" not in page


def test_artist_with_space_in_id_is_reachable(tmp_path):
    # Regression: an artist named "The Streets" produces a file at
    # "The%20Streets.html" (literal '%'). Hrefs pointing at it must
    # double-encode so a server URL-decodes back to the on-disk name.
    config = GreatConfig(
        lists=[
            ListConfig(name="albums", kind="album"),
            ListConfig(name="artists", kind="artist"),
        ],
    )
    store = Store.init(tmp_path, config)
    store.write_items(
        "album",
        [
            Item(
                id="a1",
                kind="album",
                title="Original Pirate Material",
                creators=["The Streets"],
            ),
        ],
    )
    out = tmp_path / "dist"
    build_site(store, out)
    # The on-disk file has a literal percent sign in its name.
    assert (out / "items" / "artist" / "The%20Streets.html").is_file()
    # And every href that points at it must be double-encoded.
    artist_href = "items/artist/The%2520Streets.html"
    assert artist_href in (out / "lists" / "albums.html").read_text()
    assert (
        f"../../{artist_href}"
        in (out / "items" / "album" / "a1.html").read_text()
    )


def test_album_list_links_creator_to_artist_page(tmp_path):
    # Regression: list rows used to render creators as plain text
    # joined by commas, with no link to the artist's page.
    config = GreatConfig(
        lists=[
            ListConfig(name="albums", kind="album"),
            ListConfig(name="artists", kind="artist"),
        ],
    )
    store = Store.init(tmp_path, config)
    store.write_items(
        "album",
        [
            Item(
                id="a1",
                kind="album",
                title="Crazysexycool",
                creators=["TLC"],
            ),
        ],
    )
    out = tmp_path / "dist"
    build_site(store, out)
    page = (out / "lists" / "albums.html").read_text()
    assert '<a href="../items/artist/TLC.html">TLC</a>' in page


def test_artist_page_hides_id_when_equal_to_title(tmp_path):
    config = GreatConfig(
        lists=[
            ListConfig(name="albums", kind="album"),
            ListConfig(name="artists", kind="artist"),
        ],
    )
    store = Store.init(tmp_path, config)
    store.write_items(
        "album",
        [Item(id="a1", kind="album", title="Album", creators=["TLC"])],
    )
    out = tmp_path / "dist"
    build_site(store, out)
    page = (out / "items" / "artist" / "TLC.html").read_text()
    # Synthesized artist: id == title == "TLC". We don't want to print
    # "TLC" twice; the title line carries it.
    assert "<code>TLC</code>" not in page


def test_item_page_shows_id_when_distinct_from_title(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    store = Store.init(tmp_path, config)
    store.write_items(
        "movie",
        [Item(id="tt1", kind="movie", title="Anora")],
    )
    out = tmp_path / "dist"
    build_site(store, out)
    page = (out / "items" / "movie" / "tt1.html").read_text()
    assert "<code>tt1</code>" in page


def test_external_links_render_in_priority_order(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="albums", kind="album")])
    store = Store.init(tmp_path, config)
    store.write_items(
        "album",
        [
            Item(
                id="a1",
                kind="album",
                title="Album",
                external_ids={
                    "1001albums": "uuid",
                    "spotify": "spotify:album:1",
                    "wikipedia": "Album_(album)",
                    "tidal": "1",
                    "custom_thing": "x",
                },
            ),
        ],
    )
    out = tmp_path / "dist"
    build_site(store, out)
    page = (out / "items" / "album" / "a1.html").read_text()
    # Wikipedia (encyclopedia) before primary streamer (Spotify) before
    # secondary streamer (Tidal) before importer id (1001albums).
    # Unknown sources sort alphabetically at the end.
    positions = [
        page.find("Wikipedia"),
        page.find("Spotify"),
        page.find("Tidal"),
        page.find("1001 Albums"),
        page.find("custom_thing"),
    ]
    assert positions == sorted(positions), positions
    assert all(p != -1 for p in positions)


def test_non_artist_pages_omit_appears_on(tmp_path):
    config = GreatConfig(
        lists=[
            ListConfig(name="albums", kind="album"),
            ListConfig(name="artists", kind="artist"),
        ],
    )
    store = Store.init(tmp_path, config)
    store.write_items(
        "album",
        [
            Item(
                id="a1",
                kind="album",
                title="Crazysexycool",
                creators=["TLC"],
            ),
        ],
    )
    out = tmp_path / "dist"
    build_site(store, out)
    page = (out / "items" / "album" / "a1.html").read_text()
    assert "Appears on" not in page


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
    assert "The Bear" in html
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
    # Empty lists are hidden entirely — no list page, no index link.
    assert not (out / "lists" / "movies.html").exists()
    assert "movies" not in (out / "index.html").read_text()


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


def test_sample_data_builds(tmp_path):
    # Copy the fixture: build_site triggers Store.items() which compiles
    # derived/<kind>.toml, and we don't want that to dirty the repo.
    import shutil  # noqa: PLC0415

    repo = tmp_path / "repo"
    shutil.copytree(SAMPLE_DATA, repo)
    store = Store(repo)
    out = tmp_path / "dist"
    build_site(store, out)
    assert (out / "index.html").is_file()
    assert (out / "diary.html").is_file()
    assert (out / "queue.html").is_file()
    assert (out / "lists" / "favorites.html").is_file()
    assert (out / "items" / "movie" / "tt0068646.html").is_file()
    assert (out / "items" / "tv" / "tt11280740.html").is_file()
    diary = (out / "diary.html").read_text()
    assert "Anora" in diary
    assert "Severance" in diary


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

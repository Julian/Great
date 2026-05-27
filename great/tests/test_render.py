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


def test_diary_resolves_titles_for_unconfigured_kinds(tmp_path):
    # Repo with movies configured but NOT podcast_episode — items exist
    # on disk (as a provider importer would write them) and a log entry
    # references one. The diary must show the title, not the raw id,
    # but no per-item podcast_episode page should be emitted.
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    store = Store.init(tmp_path, config)
    episode_id = "https://example.com/feed.rss#guid-ep-1"
    store.write_items(
        "podcast_episode",
        [
            Item(
                id=episode_id,
                kind="podcast_episode",
                title="The Real Episode Title",
                parent_id="https://example.com/feed.rss",
            ),
        ],
    )
    store.append_log(
        LogEntry(
            ts=datetime(2026, 5, 9, tzinfo=UTC),
            kind="podcast_episode",
            item=episode_id,
            status="consumed",
        ),
    )
    out = tmp_path / "dist"
    build_site(store, out)
    diary = (out / "diary.html").read_text()
    assert "The Real Episode Title" in diary
    assert episode_id not in diary
    # No page should be generated for the unconfigured episode kind.
    assert not (out / "items" / "podcast_episode").exists()


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


def test_build_site_per_item_loop_scales_linearly(tmp_path):
    # Regression: the per-item-page loop used to call
    # ``data["ranked"].index(item)`` and ``item in data["ranked"]`` for
    # every (item, list) pair. Pydantic equality made each check O(N
    # fields), so a catalog with thousands of items spent most of build
    # time in quadratic ``in``/``index`` scans. A few thousand songs is
    # enough to surface the bug; the threshold is loose to stay reliable
    # in CI but well below the pre-fix runtime at this scale.
    import time  # noqa: PLC0415

    config = GreatConfig(lists=[ListConfig(name="songs", kind="song")])
    store = Store.init(tmp_path, config)
    n_items = 6000
    store.write_items(
        "song",
        [
            Item(id=f"s{n:05d}", kind="song", title=f"Song {n}")
            for n in range(n_items)
        ],
    )
    out = tmp_path / "dist"
    start = time.perf_counter()
    build_site(store, out)
    elapsed = time.perf_counter() - start
    assert elapsed < 10.0, f"build_site took {elapsed:.1f}s on {n_items} songs"
    assert (out / "items" / "song" / "s00000.html").is_file()
    assert (out / "items" / "song" / f"s{n_items - 1:05d}.html").is_file()


def test_short_list_stays_a_single_page(tmp_path, make_movies_store):
    store = make_movies_store(tmp_path)
    out = tmp_path / "dist"
    build_site(store, out)
    assert (out / "lists" / "movies.html").is_file()
    assert not (out / "lists" / "movies").exists()
    html = (out / "lists" / "movies.html").read_text()
    assert "pagination" not in html
    assert "page 1 of" not in html


def test_long_list_splits_into_multiple_pages(tmp_path):
    from great.render import LIST_PAGE_SIZE  # noqa: PLC0415

    config = GreatConfig(lists=[ListConfig(name="songs", kind="song")])
    store = Store.init(tmp_path, config)
    n_items = LIST_PAGE_SIZE * 2 + 50
    store.write_items(
        "song",
        [
            Item(id=f"s{n:05d}", kind="song", title=f"Song {n:05d}")
            for n in range(n_items)
        ],
    )
    out = tmp_path / "dist"
    build_site(store, out)

    page1 = out / "lists" / "songs.html"
    page2 = out / "lists" / "songs" / "2.html"
    page3 = out / "lists" / "songs" / "3.html"
    assert page1.is_file()
    assert page2.is_file()
    assert page3.is_file()
    assert not (out / "lists" / "songs" / "4.html").exists()

    p1 = page1.read_text()
    assert "page 1 of 3" in p1
    assert 'href="songs/2.html"' in p1
    # Item links on page 1 are one level up.
    assert "../items/song/s00000.html" in p1
    # Last id on page 1 (zero-indexed item LIST_PAGE_SIZE - 1).
    last_p1 = f"s{LIST_PAGE_SIZE - 1:05d}"
    assert last_p1 in p1

    p2 = page2.read_text()
    assert "page 2 of 3" in p2
    assert 'href="../songs.html"' in p2
    assert 'href="3.html"' in p2
    # Item links from page 2 must double-up to escape the songs/ subdir.
    first_p2 = f"s{LIST_PAGE_SIZE:05d}"
    assert f"../../items/song/{first_p2}.html" in p2


def test_pagination_links_show_window_around_current_with_ellipses(tmp_path):
    # A many-page list should not dump every page number into the
    # control: the helper shows page 1, the last page, and a two-page
    # window on each side of the current page, separated by ellipses.
    from great.render import LIST_PAGE_SIZE  # noqa: PLC0415

    config = GreatConfig(lists=[ListConfig(name="songs", kind="song")])
    store = Store.init(tmp_path, config)
    total_pages = 20
    store.write_items(
        "song",
        [
            Item(id=f"s{n:05d}", kind="song", title=f"Song {n:05d}")
            for n in range(LIST_PAGE_SIZE * total_pages)
        ],
    )
    out = tmp_path / "dist"
    build_site(store, out)

    page10 = (out / "lists" / "songs" / "10.html").read_text()
    # Two pages on each side of 10, plus first and last, with ellipses
    # bridging 1->8 and 12->20.
    for n in (1, 8, 9, 10, 11, 12, 20):
        assert f">{n}<" in page10, f"page-10 control missing page {n}"
    for n in (2, 3, 4, 5, 6, 7, 13, 14, 15, 16, 17, 18, 19):
        assert f">{n}<" not in page10, f"page-10 control unexpectedly has {n}"
    # Two ellipses (one each side of the window).
    assert page10.count("…") == 2


def test_pagination_uses_full_list_scale_for_score_bars(tmp_path):
    # The bar width compares to the largest absolute mean across the
    # full list, not just the current page. Otherwise page 2 would
    # silently re-normalize and rows would look identically intense
    # whether or not they ranked highly overall.
    from datetime import UTC, datetime  # noqa: PLC0415

    from great.render import LIST_PAGE_SIZE  # noqa: PLC0415

    config = GreatConfig(lists=[ListConfig(name="songs", kind="song")])
    store = Store.init(tmp_path, config)
    n_items = LIST_PAGE_SIZE + 5
    store.write_items(
        "song",
        [
            Item(id=f"s{n:04d}", kind="song", title=f"Song {n:04d}")
            for n in range(n_items)
        ],
    )
    # One comparison places s0000 above s0001 so the bar scale is
    # driven by a top-of-page-1 item; page 2's bars must shrink, not
    # rescale to their own (uniformly tiny) maximum.
    store.append_comparison(
        "songs",
        Comparison(
            ts=datetime(2026, 5, 27, tzinfo=UTC),
            items=["s0000", "s0001"],
            ordering=[[0], [1]],
        ),
    )
    out = tmp_path / "dist"
    build_site(store, out)

    p2 = (out / "lists" / "songs" / "2.html").read_text()
    # Every page-2 row is a tied non-participating item — bars sit at
    # the 50% midline rather than rescaling within the page.
    assert "left: 50.0%" in p2
    assert "left: 100.0%" not in p2

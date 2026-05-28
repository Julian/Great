from datetime import UTC, datetime, timedelta
from typing import get_args
import re

from typer.testing import CliRunner

from great._cli import DEFAULT_LISTS, app
from great.models import GreatConfig, Item, ItemKind, ListConfig, LogEntry
from great.session import RankingScope, run_rank_loop
from great.store import Store


def test_help_runs():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "rank personal media" in result.output.lower()


def test_show_prints_items(tmp_path, make_movies_store):
    make_movies_store(tmp_path)
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "show", "movies"],
    )
    assert result.exit_code == 0
    assert "Anora (2024)" in result.output
    assert "Casablanca (1942)" in result.output


def test_show_unknown_list(tmp_path):
    Store.init(tmp_path, GreatConfig())
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "show", "movies"],
    )
    assert result.exit_code != 0


def test_show_reflects_comparison(tmp_path, make_movies_store):
    store = make_movies_store(tmp_path)

    def session(cluster):
        by_title = {item.title: item.id for item in cluster}
        return [[by_title["Anora"]], [by_title["Casablanca"]]]

    appended = run_rank_loop(
        RankingScope.for_list(store, "movies"),
        session=session,
        max_iters=1,
    )
    assert appended == 1

    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "show", "movies"],
    )
    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert "Anora" in lines[0]
    assert "Casablanca" in lines[1]


def test_rank_command_rejects_bad_kind(tmp_path):
    Store.init(tmp_path, GreatConfig())
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "rank", "potato", "--want"],
    )
    assert result.exit_code != 0
    assert "not a valid kind" in result.output.lower()


def test_show_want_prints_want_ranking(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    store = Store.init(tmp_path, config)
    store.add_want(Item(id="w1", kind="movie", title="Wanted A"))
    store.add_want(Item(id="w2", kind="movie", title="Wanted B"))
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "show", "movie", "--want"],
    )
    assert result.exit_code == 0, result.output
    assert "Wanted A" in result.output
    assert "Wanted B" in result.output


def test_rank_command_too_few_items_exits_nonzero(
    tmp_path,
    make_movies_store,
):
    make_movies_store(
        tmp_path,
        items=[Item(id="tt1", kind="movie", title="Anora")],
    )
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "rank", "movies"],
    )
    assert result.exit_code == 1
    assert "at least" in result.output.lower()
    assert "items/movies.toml" in result.output
    assert "[[items]]" in result.output


def _make_songs_store(path):
    """Build a tiny songs catalog with two albums + an outlier artist."""
    config = GreatConfig(lists=[ListConfig(name="songs", kind="song")])
    store = Store.init(path, config)
    store.write_items(
        "album",
        [
            Item(
                id="abbey-road",
                kind="album",
                title="Abbey Road",
                creators=["The Beatles"],
            ),
            Item(
                id="revolver",
                kind="album",
                title="Revolver",
                creators=["The Beatles"],
            ),
        ],
    )
    store.write_items(
        "song",
        [
            Item(
                id="come-together",
                kind="song",
                title="Come Together",
                creators=["The Beatles"],
                parent_id="abbey-road",
            ),
            Item(
                id="something",
                kind="song",
                title="Something",
                creators=["The Beatles"],
                parent_id="abbey-road",
            ),
            Item(
                id="eleanor-rigby",
                kind="song",
                title="Eleanor Rigby",
                creators=["The Beatles"],
                parent_id="revolver",
            ),
            Item(
                id="bohemian",
                kind="song",
                title="Bohemian Rhapsody",
                creators=["Queen"],
            ),
        ],
    )
    return store


def test_rank_filters_are_mutually_exclusive(tmp_path):
    _make_songs_store(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(tmp_path),
            "rank",
            "songs",
            "--by",
            "The Beatles",
            "--from",
            "Abbey Road",
        ],
    )
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output.lower()


def test_rank_recent_rejects_with_want(tmp_path):
    _make_songs_store(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(tmp_path),
            "rank",
            "song",
            "--want",
            "--recent",
            "5",
        ],
    )
    assert result.exit_code != 0
    assert "want" in result.output.lower()


def test_rank_by_narrows_universe_in_error(tmp_path):
    _make_songs_store(tmp_path)
    # Only one Queen song → still too few items to rank, error names filter.
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "rank", "songs", "--by", "Queen"],
    )
    assert result.exit_code == 1
    assert "found 1" in result.output
    assert "by 'Queen'" in result.output
    assert "loosen" in result.output.lower()


def test_rank_from_resolves_parent_and_restricts(tmp_path):
    _make_songs_store(tmp_path)
    # Only one song in Revolver → triggers the same path, but with --from.
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "rank", "songs", "--from", "Revolver"],
    )
    assert result.exit_code == 1
    assert "found 1" in result.output
    assert "from 'Revolver'" in result.output


def test_rank_from_rejects_kind_without_parent(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    Store.init(tmp_path, config)
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "rank", "movies", "--from", "Anything"],
    )
    assert result.exit_code != 0
    assert "no parent collection" in result.output.lower()


def test_rank_recent_with_no_diary_exits_nonzero(tmp_path):
    _make_songs_store(tmp_path)
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "rank", "songs", "--recent", "5"],
    )
    assert result.exit_code == 1
    assert "no diary entries" in result.output.lower()


def test_rank_recent_rejects_zero(tmp_path):
    _make_songs_store(tmp_path)
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "rank", "songs", "--recent", "0"],
    )
    assert result.exit_code != 0
    assert "at least 1" in result.output.lower()


def test_rank_recent_seeds_from_recent_diary(tmp_path):
    store = _make_songs_store(tmp_path)
    base = datetime(2024, 1, 1, tzinfo=UTC)
    for i, song_id in enumerate(
        ["come-together", "something", "eleanor-rigby", "bohemian"],
    ):
        store.append_log(
            LogEntry(
                ts=base + timedelta(days=i),
                kind="song",
                item=song_id,
                status="consumed",
            ),
        )

    # Drive the session via the helper directly so we can observe seeds.
    from great._cli import _recent_focus_ids  # noqa: PLC0415

    songs = store.items("song")
    focus = _recent_focus_ids(store, "song", songs, n=2)
    assert focus == ["bohemian", "eleanor-rigby"]


def test_rank_recent_dedupes_and_filters_to_kind(tmp_path):
    store = _make_songs_store(tmp_path)
    # Two log entries for "something" — most-recent wins, only counted once.
    # An entry for an album kind should be ignored entirely.
    base = datetime(2024, 1, 1, tzinfo=UTC)
    store.append_log(
        LogEntry(ts=base, kind="song", item="something", status="consumed"),
    )
    store.append_log(
        LogEntry(
            ts=base + timedelta(days=1),
            kind="album",
            item="abbey-road",
            status="consumed",
        ),
    )
    store.append_log(
        LogEntry(
            ts=base + timedelta(days=2),
            kind="song",
            item="something",
            status="started",
        ),
    )
    store.append_log(
        LogEntry(
            ts=base + timedelta(days=3),
            kind="song",
            item="come-together",
            status="consumed",
        ),
    )

    from great._cli import _recent_focus_ids  # noqa: PLC0415

    songs = store.items("song")
    focus = _recent_focus_ids(store, "song", songs, n=5)
    assert focus == ["come-together", "something"]


def test_rank_by_canonicalizes_via_artist(tmp_path):
    store = _make_songs_store(tmp_path)
    # The store synthesizes a 'The Beatles' artist from songs.creators on
    # compile; --by should canonicalize a lowercase query against it.
    store.compile()

    from great._cli import _filter_by_creator  # noqa: PLC0415

    songs = store.items("song")
    ids, description = _filter_by_creator(store, songs, "the beatles")
    assert ids == {"come-together", "something", "eleanor-rigby"}
    assert "The Beatles" in description


def test_consumed_auto_creates_new_item(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    Store.init(tmp_path, config)
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(tmp_path),
            "consumed",
            "The Godfather",
            "--kind",
            "movie",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Added to items/movies: The Godfather" in result.output
    assert "Logged consumed: The Godfather" in result.output
    assert "Skipping ranking session" in result.output  # only 1 item, < MIN_K
    [item] = Store.find(tmp_path).items("movie")
    assert item.title == "The Godfather"
    [entry] = Store.find(tmp_path).log()
    assert entry.item == "The Godfather"
    assert entry.status == "consumed"


def test_consumed_requires_kind_for_unknown_title(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    Store.init(tmp_path, config)
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "consumed", "Some Brand New Thing"],
    )
    assert result.exit_code == 1
    assert "--kind" in result.output


def test_consumed_no_log_skips_diary(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    Store.init(tmp_path, config)
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(tmp_path),
            "consumed",
            "The Godfather",
            "--kind",
            "movie",
            "--no-log",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Added to items/movies: The Godfather" in result.output
    assert "Logged" not in result.output
    assert Store.find(tmp_path).log() == []


def test_consumed_existing_item_does_not_rank(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    store = Store.init(tmp_path, config)
    # Two items already — well above MIN_K, so if ranking ran it would
    # try to spawn the TUI. Existing items should never trigger that.
    store.write_items(
        "movie",
        [
            Item(id="tt1", kind="movie", title="Anora"),
            Item(id="tt2", kind="movie", title="Casablanca"),
        ],
    )
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "consumed", "Anora"],
    )
    assert result.exit_code == 0, result.output
    assert "Logged consumed: Anora" in result.output
    assert "Added to items" not in result.output
    assert "Skipping ranking session" not in result.output


def test_consumed_no_rank_skips_ranking_for_new(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    store = Store.init(tmp_path, config)
    store.write_items(
        "movie",
        [
            Item(id="tt1", kind="movie", title="Anora"),
            Item(id="tt2", kind="movie", title="Casablanca"),
        ],
    )
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(tmp_path),
            "consumed",
            "Goodfellas",
            "--kind",
            "movie",
            "--no-rank",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Added to items/movies: Goodfellas" in result.output
    assert "Skipping ranking session" not in result.output
    titles = {i.title for i in Store.find(tmp_path).items("movie")}
    assert "Goodfellas" in titles


def test_started_auto_creates_and_skips_rank_and_promote(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="tv", kind="tv")])
    store = Store.init(tmp_path, config)
    store.add_want(Item(id="Severance", kind="tv", title="Severance"))
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "started", "Severance"],
    )
    assert result.exit_code == 0, result.output
    assert "Logged started: Severance" in result.output
    assert "Skipping ranking session" not in result.output  # never ranks
    assert len(Store.find(tmp_path).wants("tv")) == 1  # not promoted


def test_started_creates_new_item_with_kind(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="tv", kind="tv")])
    Store.init(tmp_path, config)
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "started", "Andor", "--kind", "tv"],
    )
    assert result.exit_code == 0, result.output
    assert "Added to items/tv: Andor" in result.output
    assert "Logged started: Andor" in result.output
    [item] = Store.find(tmp_path).items("tv")
    assert item.title == "Andor"


def test_abandoned_logs_without_promoting(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="tv", kind="tv")])
    store = Store.init(tmp_path, config)
    store.add_want(Item(id="Severance", kind="tv", title="Severance"))
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "abandoned", "Severance"],
    )
    assert result.exit_code == 0, result.output
    assert "Logged abandoned: Severance" in result.output
    assert len(Store.find(tmp_path).wants("tv")) == 1


def test_abandoned_creates_new_item_with_kind(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="tv", kind="tv")])
    Store.init(tmp_path, config)
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "abandoned", "Andor", "--kind", "tv"],
    )
    assert result.exit_code == 0, result.output
    assert "Added to items/tv: Andor" in result.output
    assert "Logged abandoned: Andor" in result.output


def test_init_creates_layout(tmp_path):
    target = tmp_path / "media"
    result = CliRunner().invoke(app, ["init", str(target)])
    assert result.exit_code == 0
    assert (target / "great.toml").is_file()
    for sub in ("items", "comparisons", "comparisons/want", "log", "want"):
        assert (target / sub).is_dir()


def test_default_lists_cover_every_kind():
    assert {lst.kind for lst in DEFAULT_LISTS} == set(get_args(ItemKind))


def test_init_seeds_default_lists_when_no_lists(tmp_path):
    target = tmp_path / "media"
    result = CliRunner().invoke(app, ["init", str(target)])
    assert result.exit_code == 0
    store = Store.find(target)
    assert {(lst.name, lst.kind) for lst in store.config.lists} == {
        ("movies", "movie"),
        ("tv", "tv"),
        ("artists", "artist"),
        ("albums", "album"),
        ("songs", "song"),
        ("books", "book"),
        ("podcasts", "podcast"),
        ("podcast_episodes", "podcast_episode"),
        ("games", "game"),
    }
    for kind, filename in (
        ("movie", "movies"),
        ("tv", "tv"),
        ("artist", "artists"),
        ("album", "albums"),
        ("song", "songs"),
        ("book", "books"),
        ("podcast", "podcasts"),
        ("podcast_episode", "podcast_episodes"),
        ("game", "games"),
    ):
        body = (target / "items" / f"{filename}.toml").read_text()
        assert f"kind `{kind}`" in body
        assert "# [[items]]" in body
    assert not (target / "items" / "EXAMPLE.toml").exists()


def test_init_with_lists(tmp_path):
    target = tmp_path / "media"
    result = CliRunner().invoke(
        app,
        [
            "init",
            str(target),
            "--list",
            "movies:movie",
            "--list",
            "tv:tv",
        ],
    )
    assert result.exit_code == 0
    store = Store.find(target)
    assert {lst.name for lst in store.config.lists} == {"movies", "tv"}


def test_init_with_lists_points_at_items_files(tmp_path):
    target = tmp_path / "media"
    result = CliRunner().invoke(
        app,
        [
            "init",
            str(target),
            "--list",
            "favorites:movie",
            "--list",
            "watchlist:tv",
        ],
    )
    assert result.exit_code == 0
    assert "items/" in result.output
    assert "favorites" in result.output
    assert "watchlist" in result.output
    assert "great consumed" in result.output
    movie_items = (target / "items" / "movies.toml").read_text()
    tv_items = (target / "items" / "tv.toml").read_text()
    assert "# [[items]]" in movie_items
    assert "kind `movie`" in movie_items
    assert "kind `tv`" in tv_items
    assert not (target / "items" / "EXAMPLE.toml").exists()


def test_init_refuses_existing(tmp_path):
    Store.init(tmp_path, GreatConfig())
    result = CliRunner().invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 1
    assert "already exists" in result.output.lower()


def test_init_rejects_bad_spec(tmp_path):
    target = tmp_path / "media"
    result = CliRunner().invoke(
        app,
        ["init", str(target), "--list", "movies-but-no-colon"],
    )
    assert result.exit_code != 0


def test_build_command_produces_index(tmp_path):
    config = GreatConfig(
        lists=[ListConfig(name="movies", kind="movie")],
    )
    Store.init(tmp_path, config)
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "build", "--out", str(tmp_path / "dist")],
    )
    assert result.exit_code == 0
    assert (tmp_path / "dist" / "index.html").is_file()


def test_build_command_defaults_out_to_repo_root(tmp_path):
    config = GreatConfig(
        lists=[ListConfig(name="movies", kind="movie")],
    )
    Store.init(tmp_path, config)
    result = CliRunner().invoke(app, ["--root", str(tmp_path), "build"])
    assert result.exit_code == 0
    assert (tmp_path / "dist" / "index.html").is_file()


def test_init_drops_pages_workflow_by_default(tmp_path):
    target = tmp_path / "media"
    result = CliRunner().invoke(app, ["init", str(target)])
    assert result.exit_code == 0
    workflow = target / ".github" / "workflows" / "build.yml"
    assert workflow.is_file()
    body = workflow.read_text()
    assert "great build" in body
    assert "persist-credentials: false" in body
    assert "permissions: {}" in body
    matches = re.findall(
        r"uses: ([\w./-]+)@([0-9a-f]{40})",
        body,
    )
    assert len(matches) == 4
    assert {action for action, _ in matches} == {
        "actions/checkout",
        "astral-sh/setup-uv",
        "actions/upload-pages-artifact",
        "actions/deploy-pages",
    }


def test_init_skips_workflow_with_no_pages(tmp_path):
    target = tmp_path / "media"
    result = CliRunner().invoke(app, ["init", str(target), "--no-pages"])
    assert result.exit_code == 0
    assert not (target / ".github").exists()


def test_diary_command_lists_entries_most_recent_first(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    store = Store.init(tmp_path, config)
    store.write_items(
        "movie",
        [
            Item(id="tt1", kind="movie", title="Anora"),
            Item(id="tt2", kind="movie", title="Casablanca"),
        ],
    )
    CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "consumed", "Anora", "--at", "2026-04-10"],
    )
    CliRunner().invoke(
        app,
        [
            "--root",
            str(tmp_path),
            "log",
            "Casablanca",
            "--status",
            "started",
            "--at",
            "2026-04-20",
            "--notes",
            "first half",
        ],
    )
    result = CliRunner().invoke(app, ["--root", str(tmp_path), "diary"])
    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert lines[0].startswith("2026-04-20")
    assert "Casablanca (movie)" in lines[0]
    assert "started" in lines[0]
    assert "first half" in lines[0]
    assert lines[1].startswith("2026-04-10")
    assert "Anora (movie)" in lines[1]
    assert "consumed" in lines[1]


def test_diary_command_year_filter(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    store = Store.init(tmp_path, config)
    store.write_items("movie", [Item(id="tt1", kind="movie", title="Anora")])
    CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "consumed", "Anora", "--at", "2025-06-01"],
    )
    CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "consumed", "Anora", "--at", "2026-06-01"],
    )
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "diary", "--year", "2025"],
    )
    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert len(lines) == 1
    assert lines[0].startswith("2025-06-01")


def test_diary_command_empty(tmp_path):
    Store.init(tmp_path, GreatConfig())
    result = CliRunner().invoke(app, ["--root", str(tmp_path), "diary"])
    assert result.exit_code == 0
    assert "no diary entries" in result.output.lower()


def test_lists_command_enumerates(tmp_path):
    config = GreatConfig(
        lists=[
            ListConfig(name="movies", kind="movie", description="favorites"),
            ListConfig(name="tv", kind="tv"),
        ],
    )
    Store.init(tmp_path, config)
    result = CliRunner().invoke(app, ["--root", str(tmp_path), "lists"])
    assert result.exit_code == 0
    assert "movies" in result.output
    assert "favorites" in result.output
    assert "tv" in result.output


def test_lists_empty(tmp_path):
    Store.init(tmp_path, GreatConfig())
    result = CliRunner().invoke(app, ["--root", str(tmp_path), "lists"])
    assert result.exit_code == 0
    assert "no lists" in result.output.lower()


def test_show_unknown_list_friendly_error(tmp_path):
    Store.init(tmp_path, GreatConfig())
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "show", "movies"],
    )
    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "movies" in (result.output + (result.stderr or ""))


def test_show_outside_repo_friendly_error(tmp_path):
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "show", "movies"],
    )
    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "great.toml" in (result.output + (result.stderr or ""))


def test_show_includes_tier_after_comparisons(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    store = Store.init(tmp_path, config)
    store.write_items(
        "movie",
        [
            Item(id="tt1", kind="movie", title="Anora"),
            Item(id="tt2", kind="movie", title="Casablanca"),
        ],
    )
    run_rank_loop(
        RankingScope.for_list(store, "movies"),
        session=lambda cluster: [[cluster[0].id], [cluster[1].id]],
        max_iters=1,
    )
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "show", "movies"],
    )
    assert result.exit_code == 0
    assert "[S]" in result.output  # winner gets top tier


def test_show_omits_tier_at_cold_start(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    store = Store.init(tmp_path, config)
    store.write_items(
        "movie",
        [Item(id="tt1", kind="movie", title="Anora")],
    )
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "show", "movies"],
    )
    assert result.exit_code == 0
    assert "[S]" not in result.output
    assert "[D]" not in result.output


def test_show_stable_sort_for_cold_start(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    store = Store.init(tmp_path, config)
    store.write_items(
        "movie",
        [
            Item(id="z", kind="movie", title="Zodiac"),
            Item(id="a", kind="movie", title="Anora"),
            Item(id="m", kind="movie", title="Memento"),
        ],
    )
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "show", "movies"],
    )
    assert result.exit_code == 0
    titles = [
        line.strip().split(".", 1)[1].strip().split("  ")[0]
        for line in result.output.splitlines()
        if line.strip() and line.strip()[0].isdigit()
    ]
    assert titles == ["Anora", "Memento", "Zodiac"]

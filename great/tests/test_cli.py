from typing import get_args
import re

from typer.testing import CliRunner

from great._cli import DEFAULT_LISTS, app
from great.models import GreatConfig, Item, ItemKind, ListConfig
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

    appended = run_rank_loop(
        RankingScope.for_list(store, "movies"),
        session=lambda _cluster: [[0], [1]],
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


def test_add_command_appends_and_skips_ranking_when_too_few(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    Store.init(tmp_path, config)
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "add", "movies", "The Godfather"],
    )
    assert result.exit_code == 0, result.output
    assert "Added to items/movies: The Godfather" in result.output
    assert "Skipping ranking session" in result.output
    [item] = Store.find(tmp_path).items("movie")
    assert item.title == "The Godfather"


def test_add_command_skips_existing_titles(tmp_path):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    store = Store.init(tmp_path, config)
    store.write_items(
        "movie",
        [Item(id="Anora", kind="movie", title="Anora")],
    )
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "add", "movies", "Anora"],
    )
    assert result.exit_code == 0, result.output
    assert "Already in items/movies: Anora" in result.output
    assert len(Store.find(tmp_path).items("movie")) == 1


def test_add_command_unknown_list_friendly_error(tmp_path):
    Store.init(tmp_path, GreatConfig())
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "add", "movies", "Anora"],
    )
    assert result.exit_code == 1
    assert "Traceback" not in result.output


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
    assert "great rank" in result.output
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
        session=lambda _cluster: [[0], [1]],
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

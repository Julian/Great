import re

from typer.testing import CliRunner
import pytest

from great._cli import (
    InsufficientItemsError,
    app,
    run_rank_loop,
)
from great.models import GreatConfig, Item, ListConfig
from great.store import Store


def _setup_movies(tmp_path, items=None):
    config = GreatConfig(lists=[ListConfig(name="movies", kind="movie")])
    store = Store.init(tmp_path, config)
    if items is None:
        items = [
            Item(id="tt1", kind="movie", title="Anora", year=2024),
            Item(id="tt2", kind="movie", title="Casablanca", year=1942),
        ]
    store.write_items("movie", items)
    return store


def test_help_runs():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "rank personal media" in result.output.lower()


def test_show_prints_items(tmp_path):
    _setup_movies(tmp_path)
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


def test_show_reflects_comparison(tmp_path):
    store = _setup_movies(tmp_path)

    appended = run_rank_loop(
        store,
        "movies",
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


def test_run_rank_loop_records_comparison(tmp_path):
    store = _setup_movies(tmp_path)

    appended = run_rank_loop(
        store,
        "movies",
        session=lambda _cluster: [[0], [1]],
        max_iters=1,
    )

    assert appended == 1
    [c] = store.comparisons("movies")
    assert c.ordering == [[0], [1]]


def test_run_rank_loop_session_can_signal_quit(tmp_path):
    store = _setup_movies(tmp_path)

    appended = run_rank_loop(
        store,
        "movies",
        session=lambda _cluster: None,
        max_iters=10,
    )

    assert appended == 0
    assert store.comparisons("movies") == []


def test_run_rank_loop_records_tie(tmp_path):
    store = _setup_movies(tmp_path)

    run_rank_loop(
        store,
        "movies",
        session=lambda cluster: [list(range(len(cluster)))],
        max_iters=1,
    )

    [c] = store.comparisons("movies")
    assert c.ordering == [[0, 1]]


def test_run_rank_loop_refuses_too_few_items(tmp_path):
    _setup_movies(
        tmp_path,
        items=[Item(id="tt1", kind="movie", title="Anora")],
    )
    store = Store.find(tmp_path)

    with pytest.raises(InsufficientItemsError):
        run_rank_loop(
            store,
            "movies",
            session=lambda _cluster: None,
            max_iters=1,
        )


def test_rank_command_too_few_items_exits_nonzero(tmp_path):
    _setup_movies(
        tmp_path,
        items=[Item(id="tt1", kind="movie", title="Anora")],
    )
    result = CliRunner().invoke(
        app,
        ["--root", str(tmp_path), "rank", "movies"],
    )
    assert result.exit_code == 1
    assert "at least" in result.output.lower()


def test_init_creates_layout(tmp_path):
    target = tmp_path / "media"
    result = CliRunner().invoke(app, ["init", str(target)])
    assert result.exit_code == 0
    assert (target / "great.toml").is_file()
    for sub in ("items", "comparisons", "log", "want"):
        assert (target / sub).is_dir()


def test_init_seeds_commented_template_when_no_lists(tmp_path):
    target = tmp_path / "media"
    result = CliRunner().invoke(app, ["init", str(target)])
    assert result.exit_code == 0
    body = (target / "great.toml").read_text()
    assert "# [[lists]]" in body
    assert 'kind = "movie"' in body
    assert "items/<kind>.toml" in body
    assert "# [[items]]" in body
    store = Store.find(target)
    assert store.config.lists == []


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
        ["init", str(target), "--list", "favorites:movie", "--list",
         "watchlist:tv"],
    )
    assert result.exit_code == 0
    assert "items/movie.toml" in result.output
    assert "items/tv.toml" in result.output
    assert "great rank" in result.output


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
        store,
        "movies",
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

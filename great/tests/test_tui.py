import pytest

from great.models import Item
from great.session import SKIP
from great.tui import RankApp


def _movies(*ids: str) -> list[Item]:
    return [Item(id=i, kind="movie", title=i) for i in ids]


def test_row_label_includes_parent_title_when_present():
    episode = Item(
        id="https://example.com/feed.rss#guid-1",
        kind="podcast_episode",
        title="Ep 1",
        parent_id="https://example.com/feed.rss",
        metadata={"parent_title": "The Example Show"},
    )
    label = RankApp._row_label(0, episode)
    assert "Ep 1" in label
    assert "The Example Show" in label


def test_row_label_omits_parent_when_metadata_missing():
    movie = Item(id="tt1", kind="movie", title="Anora", year=2024)
    label = RankApp._row_label(0, movie)
    assert "Anora" in label
    assert "(2024)" in label
    assert "—" not in label


@pytest.mark.asyncio
async def test_submit_initial_order():
    app = RankApp(_movies("a", "b", "c"))
    async with app.run_test() as pilot:
        await pilot.press("enter")
    assert app.result == [["a"], ["b"], ["c"]]


@pytest.mark.asyncio
async def test_move_first_item_down():
    app = RankApp(_movies("a", "b", "c"))
    async with app.run_test() as pilot:
        await pilot.press("J")
        await pilot.press("enter")
    assert app.result == [["b"], ["a"], ["c"]]


@pytest.mark.asyncio
async def test_move_third_item_to_top():
    app = RankApp(_movies("a", "b", "c", "d"))
    async with app.run_test() as pilot:
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("K")
        await pilot.press("K")
        await pilot.press("K")
        await pilot.press("enter")
    assert app.result == [["d"], ["a"], ["b"], ["c"]]


@pytest.mark.asyncio
async def test_move_at_boundary_is_noop():
    app = RankApp(_movies("a", "b"))
    async with app.run_test() as pilot:
        await pilot.press("K")
        await pilot.press("enter")
    assert app.result == [["a"], ["b"]]


@pytest.mark.asyncio
async def test_tie_submits_single_group():
    app = RankApp(_movies("a", "b", "c"))
    async with app.run_test() as pilot:
        await pilot.press("t")
    assert app.result == [["a", "b", "c"]]


@pytest.mark.asyncio
async def test_tie_rest_ties_focused_through_bottom():
    """``=`` at position 2 ties items 2-5 into one group below the standout."""
    app = RankApp(_movies("a", "b", "c", "d", "e"))
    async with app.run_test() as pilot:
        await pilot.press("j")
        await pilot.press("equals_sign")
        await pilot.press("enter")
    assert app.result == [["a"], ["b", "c", "d", "e"]]


@pytest.mark.asyncio
async def test_tie_rest_then_split_creates_two_subgroups():
    """``=`` again further down splits the existing tie group at the focus."""
    app = RankApp(_movies("a", "b", "c", "d", "e"))
    async with app.run_test() as pilot:
        await pilot.press("j")
        await pilot.press("equals_sign")
        await pilot.press("j", "j")
        await pilot.press("equals_sign")
        await pilot.press("enter")
    assert app.result == [["a"], ["b", "c"], ["d", "e"]]


@pytest.mark.asyncio
async def test_tie_rest_at_group_start_undoes_it():
    """Pressing ``=`` again at the group's start clears it."""
    app = RankApp(_movies("a", "b", "c", "d"))
    async with app.run_test() as pilot:
        await pilot.press("j")
        await pilot.press("equals_sign")
        await pilot.press("equals_sign")
        await pilot.press("enter")
    assert app.result == [["a"], ["b"], ["c"], ["d"]]


@pytest.mark.asyncio
async def test_tie_rest_at_bottom_is_noop():
    app = RankApp(_movies("a", "b", "c"))
    async with app.run_test() as pilot:
        await pilot.press("j", "j")
        await pilot.press("equals_sign")
        await pilot.press("enter")
    assert app.result == [["a"], ["b"], ["c"]]


@pytest.mark.asyncio
async def test_group_start_class_marks_boundaries_when_tied():
    """Leaders of groups [[a], [b, c], [d, e]] get a divider above them."""
    app = RankApp(_movies("a", "b", "c", "d", "e"))
    async with app.run_test() as pilot:
        await pilot.press("j")
        await pilot.press("equals_sign")
        await pilot.press("j", "j")
        await pilot.press("equals_sign")
        rows = list(app.query("ListItem"))
        classes = [row.has_class("group-start") for row in rows]
    assert classes == [False, True, False, True, False]


@pytest.mark.asyncio
async def test_group_start_class_absent_when_all_strict():
    app = RankApp(_movies("a", "b", "c"))
    async with app.run_test():
        rows = list(app.query("ListItem"))
        classes = [row.has_class("group-start") for row in rows]
    assert classes == [False, False, False]


@pytest.mark.asyncio
async def test_tie_rest_at_top_ties_everything():
    """``=`` on the first row collapses the whole cluster — same as ``t``."""
    app = RankApp(_movies("a", "b", "c"))
    async with app.run_test() as pilot:
        await pilot.press("equals_sign")
        await pilot.press("enter")
    assert app.result == [["a", "b", "c"]]


@pytest.mark.asyncio
async def test_number_sends_focused_item_to_rank():
    app = RankApp(_movies("a", "b", "c", "d"))
    async with app.run_test() as pilot:
        await pilot.press("j", "j", "j")
        await pilot.press("1")
        await pilot.press("enter")
    assert app.result == [["d"], ["a"], ["b"], ["c"]]


@pytest.mark.asyncio
async def test_number_cursor_lands_on_row_below_placed():
    app = RankApp(_movies("a", "b", "c", "d"))
    async with app.run_test() as pilot:
        await pilot.press("j", "j", "j")
        await pilot.press("1")
        await pilot.press("J")
        await pilot.press("enter")
    assert app.result == [["d"], ["b"], ["a"], ["c"]]


@pytest.mark.asyncio
async def test_number_to_last_position_leaves_cursor_on_placed():
    app = RankApp(_movies("a", "b", "c"))
    async with app.run_test() as pilot:
        await pilot.press("3")
        await pilot.press("K")
        await pilot.press("enter")
    assert app.result == [["b"], ["a"], ["c"]]


@pytest.mark.asyncio
async def test_number_out_of_range_is_noop():
    app = RankApp(_movies("a", "b", "c"))
    async with app.run_test() as pilot:
        await pilot.press("5")
        await pilot.press("enter")
    assert app.result == [["a"], ["b"], ["c"]]


@pytest.mark.asyncio
async def test_cancel_returns_none():
    app = RankApp(_movies("a", "b"))
    async with app.run_test() as pilot:
        await pilot.press("q")
    assert app.result is None


@pytest.mark.asyncio
async def test_skip_returns_skip_sentinel():
    app = RankApp(_movies("a", "b", "c"))
    async with app.run_test() as pilot:
        await pilot.press("s")
    assert app.result == SKIP


@pytest.mark.asyncio
async def test_open_opens_focused_item_via_player(monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(
        "webbrowser.open",
        lambda url, new=0: opened.append(url),
    )
    items = [
        Item(
            id="spotify:track:abc",
            kind="song",
            title="A",
            external_ids={"spotify": "spotify:track:abc"},
        ),
        Item(
            id="spotify:track:xyz",
            kind="song",
            title="B",
            external_ids={"spotify": "spotify:track:xyz"},
        ),
    ]
    app = RankApp(items)
    async with app.run_test() as pilot:
        await pilot.press("j")
        await pilot.press("o")
    assert opened == ["https://open.spotify.com/track/xyz"]


@pytest.mark.asyncio
async def test_open_is_noop_when_player_returns_none(monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(
        "webbrowser.open",
        lambda url, new=0: opened.append(url),
    )
    app = RankApp(_movies("a", "b", "c"))
    async with app.run_test() as pilot:
        await pilot.press("o")
    assert opened == []


@pytest.mark.asyncio
async def test_open_uses_custom_player(monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(
        "webbrowser.open",
        lambda url, new=0: opened.append(url),
    )
    app = RankApp(
        _movies("a", "b"),
        player=lambda item: f"https://example.test/{item.id}",
    )
    async with app.run_test() as pilot:
        await pilot.press("o")
    assert opened == ["https://example.test/a"]

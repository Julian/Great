import pytest

from great.models import Item
from great.tui import RankApp


def _movies(*ids: str) -> list[Item]:
    return [Item(id=i, kind="movie", title=i) for i in ids]


@pytest.mark.asyncio
async def test_submit_initial_order():
    app = RankApp(_movies("a", "b", "c"))
    async with app.run_test() as pilot:
        await pilot.press("enter")
    assert app.result == [[0], [1], [2]]


@pytest.mark.asyncio
async def test_move_first_item_down():
    app = RankApp(_movies("a", "b", "c"))
    async with app.run_test() as pilot:
        await pilot.press("J")
        await pilot.press("enter")
    assert app.result == [[1], [0], [2]]


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
    assert app.result == [[3], [0], [1], [2]]


@pytest.mark.asyncio
async def test_move_at_boundary_is_noop():
    app = RankApp(_movies("a", "b"))
    async with app.run_test() as pilot:
        await pilot.press("K")
        await pilot.press("enter")
    assert app.result == [[0], [1]]


@pytest.mark.asyncio
async def test_tie_submits_single_group():
    app = RankApp(_movies("a", "b", "c"))
    async with app.run_test() as pilot:
        await pilot.press("t")
    assert app.result == [[0, 1, 2]]


@pytest.mark.asyncio
async def test_number_sends_focused_item_to_rank():
    app = RankApp(_movies("a", "b", "c", "d"))
    async with app.run_test() as pilot:
        await pilot.press("j", "j", "j")
        await pilot.press("1")
        await pilot.press("enter")
    assert app.result == [[3], [0], [1], [2]]


@pytest.mark.asyncio
async def test_number_cursor_lands_on_row_below_placed():
    app = RankApp(_movies("a", "b", "c", "d"))
    async with app.run_test() as pilot:
        await pilot.press("j", "j", "j")
        await pilot.press("1")
        await pilot.press("J")
        await pilot.press("enter")
    assert app.result == [[3], [1], [0], [2]]


@pytest.mark.asyncio
async def test_number_to_last_position_leaves_cursor_on_placed():
    app = RankApp(_movies("a", "b", "c"))
    async with app.run_test() as pilot:
        await pilot.press("3")
        await pilot.press("K")
        await pilot.press("enter")
    assert app.result == [[1], [0], [2]]


@pytest.mark.asyncio
async def test_number_out_of_range_is_noop():
    app = RankApp(_movies("a", "b", "c"))
    async with app.run_test() as pilot:
        await pilot.press("5")
        await pilot.press("enter")
    assert app.result == [[0], [1], [2]]


@pytest.mark.asyncio
async def test_cancel_returns_none():
    app = RankApp(_movies("a", "b"))
    async with app.run_test() as pilot:
        await pilot.press("q")
    assert app.result is None

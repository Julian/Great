"""
Textual ranking session.

A user runs `great rank <list>`, the engine selects a cluster of
items, and we pop a Textual app that lets the user reorder the
cluster from best to worst (j/k navigates, J/K moves the focused
item, ``t`` declares the whole cluster a tie, Enter submits, q/Esc
cancels).
"""

from collections.abc import Callable
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Label, ListItem, ListView

from great.models import Item

RankResult = list[list[int]] | None
Session = Callable[[list[Item]], RankResult]


class RankApp(App):
    """Reorderable list for ranking a cluster of items."""

    CSS = """
    Screen { align: center middle; }
    ListView { width: 80%; height: auto; border: round $accent; }
    #hint { padding: 1; color: $text-muted; }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("j,down", "cursor_down", "Down"),
        Binding("k,up", "cursor_up", "Up"),
        Binding("J,shift+down", "move_down", "Move ↓", priority=True),
        Binding("K,shift+up", "move_up", "Move ↑", priority=True),
        Binding("t", "tie", "Tie", priority=True),
        Binding("enter", "submit", "Submit", priority=True),
        Binding("q,escape", "cancel", "Cancel", priority=True),
    ]

    def __init__(self, items: list[Item]):
        super().__init__()
        self._items = items
        self._order: list[int] = list(range(len(items)))
        self.result: RankResult = None

    def compose(self) -> ComposeResult:
        """Build the screen layout."""
        yield Header()
        yield Label(
            "Rank from best to worst. "
            "j/k focus, J/K move, t=tie, Enter submit, q cancel.",
            id="hint",
        )
        yield ListView(
            *self._build_items(),
            id="rank-list",
        )
        yield Footer()

    def _build_items(self) -> list[ListItem]:
        return [
            ListItem(Label(self._row_label(rank, self._items[idx])))
            for rank, idx in enumerate(self._order)
        ]

    @staticmethod
    def _row_label(rank: int, item: Item) -> str:
        suffix = f" ({item.year})" if item.year is not None else ""
        return f"{rank + 1:2d}. {item.title}{suffix}"

    @property
    def _list(self) -> ListView:
        return self.query_one("#rank-list", ListView)

    def _refresh(self, focus: int) -> None:
        self._list.clear()
        self._list.extend(self._build_items())
        self._list.index = focus

    def action_cursor_down(self) -> None:
        """Move focus down."""
        self._list.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move focus up."""
        self._list.action_cursor_up()

    def action_move_down(self) -> None:
        """Move the focused item down one rank."""
        idx = self._list.index or 0
        if idx + 1 < len(self._order):
            self._order[idx], self._order[idx + 1] = (
                self._order[idx + 1],
                self._order[idx],
            )
            self._refresh(idx + 1)

    def action_move_up(self) -> None:
        """Move the focused item up one rank."""
        idx = self._list.index or 0
        if idx > 0:
            self._order[idx], self._order[idx - 1] = (
                self._order[idx - 1],
                self._order[idx],
            )
            self._refresh(idx - 1)

    def action_tie(self) -> None:
        """Submit the cluster as a single indistinguishable tie group."""
        self.result = [list(self._order)]
        self.exit()

    def action_submit(self) -> None:
        """Submit the current order as a fully-ranked comparison."""
        self.result = [[i] for i in self._order]
        self.exit()

    def action_cancel(self) -> None:
        """Cancel without recording a comparison."""
        self.result = None
        self.exit()


def run_rank_session(items: list[Item]) -> RankResult:
    """Run the TUI synchronously; return ordering or ``None`` on cancel."""
    app = RankApp(items)
    app.run()
    return app.result

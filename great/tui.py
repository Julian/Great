"""
Textual ranking session.

A user runs `great rank <list>`, the engine selects a cluster of
items, and we pop a Textual app that lets the user reorder the
cluster from best to worst (j/k navigates, J/K moves the focused
item, ``=`` makes the focused item the start of a tie group that
runs to the bottom (press again at the same position to undo;
press ``=`` further down to split off a sub-group), ``t``
declares the whole cluster a tie, ``s`` skips the cluster and
asks for another, Enter submits, q/Esc cancels).
"""

from typing import ClassVar

from rich.markup import escape
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Label, ListItem, ListView

from great.models import Item
from great.session import SKIP, RankResult, Session

__all__ = ["RankApp", "RankResult", "Session", "run_rank_session"]


class RankApp(App):
    """Reorderable list for ranking a cluster of items."""

    CSS = """
    Screen { align: center middle; }
    ListView { width: 80%; height: auto; border: round $accent; }
    ListItem.group-start { border-top: dashed $accent; }
    #hint { padding: 1; color: $text-muted; }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("j,down", "cursor_down", "Down"),
        Binding("k,up", "cursor_up", "Up"),
        Binding("J,shift+down", "move_down", "Move ↓", priority=True),
        Binding("K,shift+up", "move_up", "Move ↑", priority=True),
        Binding("1", "move_to(1)", "→ rank", priority=True, show=True),
        *(
            Binding(str(n), f"move_to({n})", "", priority=True, show=False)
            for n in range(2, 10)
        ),
        Binding("equals_sign", "tie_rest", "Tie rest", priority=True),
        Binding("t", "tie", "Tie all", priority=True),
        Binding("s", "skip", "Skip", priority=True),
        Binding("enter", "submit", "Submit", priority=True),
        Binding("q,escape", "cancel", "Cancel", priority=True),
    ]

    def __init__(self, items: list[Item]):
        super().__init__()
        self._items = items
        self._order: list[int] = list(range(len(items)))
        # _tied[i] is True when position i is tied with position i-1.
        # _tied[0] is always False (no boundary above position 0).
        self._tied: list[bool] = [False] * len(items)
        self.result: RankResult = None

    def compose(self) -> ComposeResult:
        """Build the screen layout."""
        yield Header()
        yield Label(
            "Rank from best to worst. "
            "j/k focus, J/K move, 1-9 send to rank, "
            "==tie rest below, t=tie all, s=skip, Enter submit, q cancel.",
            id="hint",
        )
        yield ListView(
            *self._build_items(),
            id="rank-list",
        )
        yield Footer()

    def _build_items(self) -> list[ListItem]:
        ranks = self._display_ranks()
        has_ties = any(self._tied)
        rows: list[ListItem] = []
        for pos, idx in enumerate(self._order):
            label = self._row_label(ranks[pos], self._items[idx])
            row = ListItem(Label(label))
            if has_ties and pos > 0 and not self._tied[pos]:
                row.add_class("group-start")
            rows.append(row)
        return rows

    def _display_ranks(self) -> list[int]:
        """1-indexed competition ranks (e.g. ``[1, 2, 2, 4]``)."""
        ranks: list[int] = []
        current = 1
        for i in range(len(self._order)):
            if i > 0 and not self._tied[i]:
                current = i + 1
            ranks.append(current)
        return ranks

    @staticmethod
    def _row_label(display_rank: int, item: Item) -> str:
        suffix = f" ({item.year})" if item.year is not None else ""
        byline = (
            f"[italic dim]{escape(', '.join(item.creators))}[/] "
            if item.creators
            else ""
        )
        parent_title = item.metadata.get("parent_title")
        parent = (
            f" [dim]— {escape(str(parent_title))}[/]" if parent_title else ""
        )
        return (
            f"{display_rank:2d}. {byline}{escape(item.title)}{suffix}{parent}"
        )

    @property
    def _list(self) -> ListView:
        return self.query_one("#rank-list", ListView)

    def _swap(self, a: int, b: int) -> None:
        self._order[a], self._order[b] = self._order[b], self._order[a]
        ranks = self._display_ranks()
        children = self._list.children
        for pos in (a, b):
            label = children[pos].query_one(Label)
            label.update(
                self._row_label(ranks[pos], self._items[self._order[pos]]),
            )

    def _refresh_labels(self) -> None:
        ranks = self._display_ranks()
        has_ties = any(self._tied)
        children = self._list.children
        for pos, idx in enumerate(self._order):
            row = children[pos]
            row.query_one(Label).update(
                self._row_label(ranks[pos], self._items[idx]),
            )
            if has_ties and pos > 0 and not self._tied[pos]:
                row.add_class("group-start")
            else:
                row.remove_class("group-start")

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
            self._swap(idx, idx + 1)
            self._list.action_cursor_down()

    def action_move_up(self) -> None:
        """Move the focused item up one rank."""
        idx = self._list.index or 0
        if idx > 0:
            self._swap(idx - 1, idx)
            self._list.action_cursor_up()

    def action_move_to(self, position: int) -> None:
        """
        Send the focused item to rank ``position`` (1-indexed).

        No-op when ``position`` is outside the current cluster size.
        """
        target = position - 1
        if not 0 <= target < len(self._order):
            return
        while (self._list.index or 0) > target:
            self.action_move_up()
        while (self._list.index or 0) < target:
            self.action_move_down()
        if target + 1 < len(self._order):
            self._list.action_cursor_down()

    def action_tie_rest(self) -> None:
        """
        Tie the focused item with everything below into one group.

        Pressing again at the same position (when this position
        already starts a tie group running to the bottom) splits
        every item below back into singletons, leaving groups above
        the focus untouched.
        """
        idx = self._list.index or 0
        n = len(self._order)
        if idx + 1 >= n:
            return
        already_one_group = not self._tied[idx] and all(
            self._tied[i] for i in range(idx + 1, n)
        )
        for i in range(idx + 1, n):
            self._tied[i] = not already_one_group
        if not already_one_group:
            self._tied[idx] = False
        self._refresh_labels()

    def action_tie(self) -> None:
        """Submit the cluster as a single indistinguishable tie group."""
        self.result = [list(self._order)]
        self.exit()

    def action_skip(self) -> None:
        """Discard this cluster without recording and request another."""
        self.result = SKIP
        self.exit()

    def action_submit(self) -> None:
        """Submit the current order, collapsing tied-with-above runs."""
        groups: list[list[int]] = []
        for pos, idx in enumerate(self._order):
            if pos > 0 and self._tied[pos]:
                groups[-1].append(idx)
            else:
                groups.append([idx])
        self.result = groups
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

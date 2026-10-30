"""Bottom status bar: branch, sync state, counts, key hints."""

from __future__ import annotations

from textual.containers import Horizontal
from textual.widgets import Static

from .. import keys
from ..models import RepoStatus


class StatusBar(Horizontal):
    def compose(self):
        yield Static("", id="sb-branch")
        yield Static("", id="sb-sync")
        yield Static("", id="sb-counts")
        yield Static("", id="sb-keys")

    def on_mount(self) -> None:
        hints = "  ".join(
            f"[#7aa2f7 on #232f47] {k} [/] {d}" for k, d in keys.STATUS_BAR_KEYS
        )
        self.query_one("#sb-keys", Static).update(hints)

    def update_status(self, st: RepoStatus, busy: bool = False) -> None:
        if st.head:
            branch_color = "#e0af68" if st.head_detached else "#9ece6a"
            branch = f"[bold {branch_color}] ⎇ {st.head} [/]"
            if not st.has_commits:
                branch += "[dim](无提交)[/]"
            self.query_one("#sb-branch", Static).update(branch)
        parts: list[str] = []
        if st.ahead:
            parts.append(f"[bold #e0af68]↑{st.ahead}[/]")
        if st.behind:
            parts.append(f"[bold #f7768e]↓{st.behind}[/]")
        if not parts and st.upstream:
            parts.append("[dim]≡[/]")
        if busy:
            parts.append("[bold #e0af68]…[/]")
        self.query_one("#sb-sync", Static).update(" ".join(parts))
        counts = (
            f"[dim]{len(st.worktree_entries)} 改动 · "
            f"{len(st.index_entries)} 已暂存[/]"
        )
        self.query_one("#sb-counts", Static).update(counts)

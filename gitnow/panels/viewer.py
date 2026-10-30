"""Right panel: git log list / file diff / commit detail."""

from __future__ import annotations

from rich.text import Text
from textual import on
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from .. import gitbackend, theme
from ..models import LogEntry

MAX_LINES = gitbackend.MAX_DIFF_LINES


class CommitRequested(Message):
    def __init__(self, sha: str) -> None:
        self.sha = sha
        super().__init__()


class BackRequested(Message):
    pass


class LogNearEnd(Message):
    pass


class LogList(OptionList):
    BINDINGS = [
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
        Binding("enter", "open_commit", "查看提交", show=True),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.highlighted_sha: str | None = None

    @on(OptionList.OptionHighlighted)
    def _highlighted(self, event: OptionList.OptionHighlighted) -> None:
        event.stop()
        opt_id = event.option.id
        self.highlighted_sha = str(opt_id) if opt_id is not None else None
        if (
            self.highlighted is not None
            and self.option_count
            and self.option_count - self.highlighted <= 3
        ):
            self.post_message(LogNearEnd())

    def action_open_commit(self) -> None:
        if self.highlighted_sha:
            self.post_message(CommitRequested(self.highlighted_sha))


class RightViewer(VerticalScroll):
    can_focus = True

    BINDINGS = [
        Binding("j", "scroll_down", show=False),
        Binding("k", "scroll_up", show=False),
        Binding("escape", "back", show=False),
        Binding("backspace", "back", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.mode = "log"
        self.token: object = None

    def compose(self):
        yield LogList(id="log-list")
        yield Static("", id="viewer-content")

    @property
    def log_list(self) -> LogList:
        return self.query_one("#log-list", LogList)

    @property
    def content_static(self) -> Static:
        return self.query_one("#viewer-content", Static)

    # ---- log mode --------------------------------------------------------
    def populate_log(self, entries: list[LogEntry], complete: bool) -> None:
        self.mode = "log"
        self.token = None
        self.border_subtitle = "" if complete else "↓ 加载更多"
        if not entries:
            self._show_static(Text("(无提交 — 空仓库)", style=theme.FG_DIM))
            return
        prev_sha = self.log_list.highlighted_sha
        self.content_static.display = False
        self.log_list.display = True
        self.log_list.set_options([Option(self._log_line(e), id=e.sha) for e in entries])
        if prev_sha:
            try:
                idx = self.log_list.get_option_index(prev_sha)
            except Exception:
                idx = None
            if idx is not None:
                self.log_list.highlighted = idx
        if self.log_list.highlighted is None:
            self.log_list.highlighted = 0

    def show_note(self, note: str) -> None:
        self.mode = "log"
        self.log_list.display = False
        self._show_static(Text(note, style=theme.FG_DIM))

    def _log_line(self, e: LogEntry) -> Text:
        t = Text()
        t.append(f"{e.short:<7} ", style=f"bold {theme.ACCENT_ORANGE}")
        t.append(f"{e.date} ", style=theme.FG_DIM)
        t.append(f"{e.author} ", style=theme.ACCENT_CYAN)
        if e.refs:
            t.append(f"({e.refs}) ", style=f"bold {theme.ACCENT_GREEN}")
        t.append(e.subject, style=theme.FG)
        return t

    # ---- diff / commit modes ---------------------------------------------
    def apply_diff(self, path: str, badge: str, text: str, token: object) -> None:
        if token != self.token:
            return
        self.mode = "diff"
        t = Text()
        t.append(f" {badge} ", style=f"bold black on {theme.ACCENT_BLUE}")
        t.append(f" {path}\n\n", style=f"bold {theme.FG}")
        if not text.strip():
            t.append("(无改动)", style=theme.FG_DIM)
        else:
            self._append_diff(t, text)
        self._show_static(t)

    def apply_commit(self, sha: str, text: str, token: object) -> None:
        if token != self.token:
            return
        self.mode = "commit"
        t = Text()
        t.append(" commit ", style=f"bold black on {theme.ACCENT_ORANGE}")
        t.append(f" {sha[:10]}\n\n", style=f"bold {theme.FG}")
        if not text.strip():
            t.append("(无内容)", style=theme.FG_DIM)
        else:
            self._append_diff(t, text, commit_header=True)
        self._show_static(t)

    def _show_static(self, content: Text) -> None:
        self.log_list.display = False
        self.content_static.display = True
        self.content_static.update(content)
        self.scroll_home(animate=False)

    def _append_diff(self, t: Text, text: str, commit_header: bool = False) -> None:
        all_lines = text.splitlines()
        truncated = len(all_lines) > MAX_LINES
        lines = all_lines[:MAX_LINES]
        for line in lines:
            if commit_header and line.startswith("commit "):
                t.append(line + "\n", style=f"bold {theme.ACCENT_ORANGE}")
            elif commit_header and line.startswith(("Author:", "Date:", "Merge:")):
                t.append(line + "\n", style=theme.FG_DIM)
            elif line.startswith("diff --git"):
                t.append(line + "\n", style=theme.DIFF_STYLES["meta"])
            elif line.startswith(("@@",)):
                t.append(line + "\n", style=theme.DIFF_STYLES["hunk"])
            elif line.startswith(("---", "+++")):
                t.append(line + "\n", style=theme.DIFF_STYLES["range"])
            elif line.startswith("+"):
                t.append(line + "\n", style=theme.DIFF_STYLES["add"])
            elif line.startswith("-"):
                t.append(line + "\n", style=theme.DIFF_STYLES["del"])
            elif line.startswith(
                (
                    "index ", "new file mode", "deleted file mode",
                    "old mode", "new mode", "rename ", "similarity ",
                    "Binary files", "Giant binary", "GIT binary patch",
                )
            ):
                t.append(line + "\n", style=theme.DIFF_STYLES["range"])
            else:
                t.append(line + "\n")
        if truncated:
            t.append(
                f"\n… 已截断，共 {len(all_lines)} 行 (上限 {MAX_LINES})",
                style=theme.FG_DIM,
            )

    # ---- actions ----------------------------------------------------------
    def action_back(self) -> None:
        self.post_message(BackRequested())

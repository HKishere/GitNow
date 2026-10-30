"""Modal screens: commit message, confirm, help."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, TextArea

from .. import keys


class CommitModal(ModalScreen):
    BINDINGS = [
        Binding("ctrl+s", "do_commit", "提交", show=True),
        Binding("ctrl+enter", "do_commit", show=False),
        Binding("escape", "cancel", "取消", show=True),
    ]

    def __init__(self, staged_count: int, **kwargs) -> None:
        self.staged_count = staged_count
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        with Vertical(id="commit-dialog"):
            yield Static(f"提交 — {self.staged_count} 个已暂存文件", id="cm-title")
            yield TextArea(id="cm-msg")
            yield Static("输入说明 · Ctrl+S 提交 · Esc 取消", id="cm-hint")

    def on_mount(self) -> None:
        self.query_one("#cm-msg", TextArea).focus()

    def action_do_commit(self) -> None:
        message = self.query_one("#cm-msg", TextArea).text.strip()
        if not message:
            self.app.notify("提交说明不能为空", severity="warning")
            return
        self.dismiss(message)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmModal(ModalScreen):
    BINDINGS = [
        Binding("y", "confirm", "确认", show=True),
        Binding("enter", "confirm", show=False),
        Binding("n", "cancel", show=False),
        Binding("escape", "cancel", "取消", show=True),
    ]

    def __init__(self, title: str, lines: list[str], **kwargs) -> None:
        self._title = title
        self._lines = lines
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Static(Text(self._title, style="bold #f7768e"), id="cf-title")
            yield Static("\n".join(self._lines), id="cf-body")
            yield Static("y 确认 · Esc 取消", id="cf-hint")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class HelpModal(ModalScreen):
    BINDINGS = [
        Binding("escape", "close", "关闭", show=True),
        Binding("q", "close", show=False),
        Binding("question_mark", "close", show=False),
    ]

    def compose(self) -> ComposeResult:
        text = Text()
        for section, rows in keys.all_sections():
            text.append(f"{section}\n", style="bold #7aa2f7")
            width = max(len(k) for k, _ in rows)
            for k, d in rows:
                text.append(f"  {k:<{width}}  ", style="bold #e0af68")
                text.append(f"{d}\n", style="#c0caf5")
            text.append("\n")
        with Vertical(id="help-dialog"):
            yield Static(text, id="help-body")
    def action_close(self) -> None:
        self.dismiss(False)

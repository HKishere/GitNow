"""Modal screens: commit message, confirm, help.

三个弹窗都是 ModalScreen 子类：盖在主界面之上挡住输入，
关闭时用 dismiss(结果) 把用户的选择传回 push_screen 的回调。
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, TextArea

from .. import keys


class CommitModal(ModalScreen):
    """提交信息输入框。dismiss(message) 返回说明文字，dismiss(None) 表示取消。"""

    BINDINGS = [
        Binding("ctrl+s", "do_commit", "提交", show=True),
        Binding("ctrl+enter", "do_commit", show=False),
        Binding("escape", "cancel", "取消", show=True),
    ]

    def __init__(self, staged_count: int, **kwargs) -> None:
        # 注意：必须先赋自定义属性再调 super().__init__，
        # ModalScreen 初始化过程中可能触发 compose，属性得已就位
        self.staged_count = staged_count
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        """标题（显示已暂存文件数）+ 多行输入框 + 底部按键提示。"""
        with Vertical(id="commit-dialog"):
            yield Static(f"提交 — {self.staged_count} 个已暂存文件", id="cm-title")
            yield TextArea(id="cm-msg")
            yield Static("输入说明 · Ctrl+S 提交 · Esc 取消", id="cm-hint")

    def on_mount(self) -> None:
        """弹出后自动聚焦输入框，用户可以直接打字。"""
        self.query_one("#cm-msg", TextArea).focus()

    def action_do_commit(self) -> None:
        """Ctrl+S：取输入框内容，空说明报警告不关闭；非空则带着说明关闭弹窗。"""
        message = self.query_one("#cm-msg", TextArea).text.strip()
        if not message:
            self.app.notify("提交说明不能为空", severity="warning")
            return
        self.dismiss(message)

    def action_cancel(self) -> None:
        """Esc：取消，回调收到 None 不做任何事。"""
        self.dismiss(None)


class ConfirmModal(ModalScreen):
    """通用确认框（丢弃改动等危险操作用）。dismiss(True/False)。"""

    BINDINGS = [
        Binding("y", "confirm", "确认", show=True),
        Binding("enter", "confirm", show=False),
        Binding("n", "cancel", show=False),
        Binding("escape", "cancel", "取消", show=True),
    ]

    def __init__(self, title: str, lines: list[str], **kwargs) -> None:
        self._title = title  # 红色加粗的大标题，如"丢弃改动?"
        self._lines = lines  # 正文若干行（路径、后果说明）
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Static(Text(self._title, style="bold #f7768e"), id="cf-title")
            yield Static("\n".join(self._lines), id="cf-body")
            yield Static("y 确认 · Esc 取消", id="cf-hint")

    def action_confirm(self) -> None:
        """y/Enter：确认执行危险操作。"""
        self.dismiss(True)

    def action_cancel(self) -> None:
        """n/Esc：放弃，回调收到 False 不做任何事。"""
        self.dismiss(False)


class HelpModal(ModalScreen):
    """帮助弹窗：用 keys.all_sections() 把全部快捷键按分区渲染成对齐的两列表。"""

    BINDINGS = [
        Binding("escape", "close", "关闭", show=True),
        Binding("q", "close", show=False),
        Binding("question_mark", "close", show=False),
    ]

    def compose(self) -> ComposeResult:
        """逐分区渲染：蓝色分区标题，每行"黄色按键列（按最长键名对齐）+ 白说明"。"""
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
        """Esc/q/?：关闭帮助（dismiss 值无所谓，调用方忽略回调结果）。"""
        self.dismiss(False)

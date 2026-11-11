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
from .statusbar import PanelFocused

MAX_LINES = gitbackend.MAX_DIFF_LINES  # diff 详情最多渲染的行数（超出截断）


class CommitRequested(Message):
    """用户在 log 列表里按 Enter，想查看某个提交的详情。

    LogList 自己不加载内容（它没有仓库访问能力），只发消息带 sha，
    由 App 层去后台取 git show 结果再回填。
    """

    def __init__(self, sha: str) -> None:
        self.sha = sha
        super().__init__()


class BackRequested(Message):
    """用户按 Esc/Backspace，想退出当前视图（commit → log，或 diff → 取消选中）。"""


class LogNearEnd(Message):
    """光标滚到 log 列表末尾 3 条以内，请求加载下一页（无限滚动）。"""


class LogList(OptionList):
    """log 列表：每个 option 是一行 commit（短SHA 日期 作者 分支 标题）。"""

    BINDINGS = [
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
        Binding("enter", "open_commit", "查看提交", show=True),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.highlighted_sha: str | None = None  # 当前高亮提交的完整 SHA

    @on(OptionList.OptionHighlighted)
    def _highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """光标移动时记录 SHA；同时检查是否临近列表末尾。

        event.stop() 阻止事件继续冒泡——否则 App 层可能把它当成
        文件高亮处理。距末尾 ≤3 条时发 LogNearEnd，让 App 提前分页，
        用户滚到底之前下一页已经就绪。
        """
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
        """Enter：请求查看当前高亮提交的详情（sha 通过消息传给 App）。"""
        if self.highlighted_sha:
            self.post_message(CommitRequested(self.highlighted_sha))

    def on_focus(self) -> None:
        """log 列表获得焦点：状态栏提示切到 log 上下文。"""
        self.post_message(PanelFocused("log"))


class RightViewer(VerticalScroll):
    """右侧查看器，三种互斥视图（mode 字段标记）：

      "log"    — OptionList 显示提交列表（默认）
      "diff"   — Static 显示某个文件的工作区/暂存区/未跟踪 diff
      "commit" — Static 显示某次提交的完整 show 输出

    token 机制解决"慢操作竞态"：每次切换选中时 App 会设置一个 token
    （(来源, 路径或sha) 元组），后台线程加载完成后回填时校验
    token 是否还是当前值——不一致说明用户已经又切到别处了，
    丢弃这次结果，防止旧内容覆盖新内容。
    """

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
        self.token: object = None  # 当前视图的"身份凭证"，见类注释

    def compose(self):
        # 两个子视图并存，用 display 互斥切换（比销毁重建便宜，状态也保留）
        yield LogList(id="log-list")
        yield Static("", id="viewer-content")

    @property
    def log_list(self) -> LogList:
        return self.query_one("#log-list", LogList)

    @property
    def content_static(self) -> Static:
        return self.query_one("#viewer-content", Static)

    def on_focus(self) -> None:
        """viewer 本体获得焦点（diff/commit 视图）：状态栏提示切到对应上下文。

        log 模式下可聚焦的是内部 log_list（有自己的 on_focus），走不到这里；
        这里只在 diff/commit 视图直接聚焦 viewer 本身时触发。
        """
        self.post_message(PanelFocused("log" if self.mode == "log" else "diff"))

    # ---- log mode --------------------------------------------------------
    def populate_log(self, entries: list[LogEntry], complete: bool) -> None:
        """把 log 条目填充进列表，切回 log 视图。

        - complete=True 表示没有更多分页了，副标题清空；否则显示"↓ 加载更多"
        - 空仓库显示占位文字
        - 刷新后尽量恢复之前的高亮位置：记住 highlighted_sha，
          填充完用 get_option_index 找回它的下标
        """
        self.mode = "log"
        self.token = None  # 离开 diff/commit 视图，作废未完成的加载
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
        """显示一条灰色占位文字（启动时"加载中…"等），本质是单行 Static 视图。"""
        self.mode = "log"
        self.log_list.display = False
        self._show_static(Text(note, style=theme.FG_DIM))

    def _log_line(self, e: LogEntry) -> Text:
        """渲染 log 列表的一行：橙短SHA + 灰日期 + 青作者 + 绿分支 + 正文标题。"""
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
        """显示文件 diff。token 与 self.token 不一致时直接丢弃（竞态保护，见类注释）。

        badge 是来源徽章文字（"已暂存"/"工作区"/"未跟踪"），告诉用户
        这个 diff 是哪两边之间的。无改动时显示"(无改动)"占位。
        """
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
        """显示提交详情（git show 输出）。竞态保护同 apply_diff。"""
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
        """切换到 Static 视图（隐藏 log 列表），更新内容并回到顶部。"""
        self.log_list.display = False
        self.content_static.display = True
        self.content_static.update(content)
        self.scroll_home(animate=False)

    def _append_diff(self, t: Text, text: str, commit_header: bool = False) -> None:
        """把 diff 文本逐行上色追加到 Text 上。

        逐行按前缀判断类型（git diff 输出格式固定）：
          commit 头（可选）: commit/Author/Date 行
          diff --git ...   → meta（蓝色加粗）
          @@ ... @@        → hunk（紫色）
          ---/+++/index 等 → range（弱化灰）
          + 开头           → add（绿字绿底）
          - 开头           → del（红字红底）
          其余             → 上下文行，默认色
        超过 MAX_LINES 行时截断并追加提示（大 diff 全渲染会卡 UI）。
        """
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
        """Esc/Backspace：请求返回上一层（发给 App 决定回到哪里）。"""
        self.post_message(BackRequested())

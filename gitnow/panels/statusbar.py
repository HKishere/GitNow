"""Bottom status bar: branch, sync state, counts, key hints."""

from __future__ import annotations

from textual.containers import Horizontal
from textual.widgets import Static

from .. import keys
from ..models import RepoStatus


class StatusBar(Horizontal):
    """底部状态栏，一行四格：分支名 | 同步状态 | 改动计数 | 按键提示。

    布局（对应 gitnow.tcss 里 #sb-* 规则）：前三格 width:auto 按内容收缩，
    最后一格 #sb-keys 占满剩余宽度并右对齐。
    内容用 rich markup 字符串（[bold xxx]...[/]）而不是 Text 对象，
    Static.update 直接接受。
    """

    def compose(self):
        # 四个 Static 由左到右：分支 / ahead-behind / 计数 / 快捷键提示
        yield Static("", id="sb-branch")
        yield Static("", id="sb-sync")
        yield Static("", id="sb-counts")
        yield Static("", id="sb-keys")

    def on_mount(self) -> None:
        """挂载时渲染按键提示（内容固定，只做一次）。每项渲染成"高亮按键块 + 说明"。"""
        hints = "  ".join(
            f"[#7aa2f7 on #232f47] {k} [/] {d}" for k, d in keys.STATUS_BAR_KEYS
        )
        self.query_one("#sb-keys", Static).update(hints)

    def update_status(self, st: RepoStatus, busy: bool = False) -> None:
        """根据 RepoStatus 刷新前三格。App 在每次 git 状态变化后调用。

        - 分支格：detached HEAD 用橙色，正常分支绿色；空仓库追加"(无提交)"
        - 同步格：↑N 本地领先 / ↓N 落后；与上游一致但有 upstream 时显示 ≡；
          busy=True（后台 git 操作进行中）再追加一个 …
        - 计数格：工作区改动数 · 已暂存数
        """
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

"""Left-bottom panel: staged (index) files."""

from __future__ import annotations

from rich.text import Text
from textual import on
from textual.binding import Binding
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from .. import theme
from ..models import RepoStatus
from .tree import FileHighlighted


class StagedPanel(OptionList):
    """左下角"已暂存"面板。

    用 Textual 的 OptionList 展示暂存区里的文件（gitui 风格绿色系前缀）。
    与 FileTreePanel 协作：两边光标事件都发同一种 FileHighlighted 消息，
    App 层根据 panel 字段决定右侧显示哪种 diff（--cached 还是工作区 diff）。
    """

    BINDINGS = [
        Binding("space", "unstage", "取消暂存", show=True),
        Binding("a", "stage_all", "全部暂存", show=False),
        Binding("u", "unstage_all", "全部取消", show=False),
        Binding("e", "edit", "编辑", show=False),
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.highlighted_path: str | None = None  # 光标停留的文件路径
        self._paths: list[str] = []               # 当前列表里的全部路径（顺序与 UI 一致）

    def rebuild(self, st: RepoStatus, keep_path: str | None = None) -> None:
        """整体重建选项列表。App 在每次 git 状态刷新后调用。

        流程：清空 → 把每个暂存条目渲染成 (状态字母+路径) 的彩色 Option →
        加入列表 → 恢复光标。恢复优先级：keep_path（App 传来的上次路径）
        > highlighted_path（面板自己记住的）；都失效就不动光标
        （首次填充时 highlighted 为 None，下面会把第一条设为高亮）。
        """
        self.clear_options()
        self._paths = []
        options: list[Option] = []
        for e in st.index_entries:
            # 状态字母上色：A/M 绿、D 红、R 紫、U 亮红（见 theme.INDEX_COLORS）
            color = theme.INDEX_COLORS.get(e.index_status, theme.FG)
            text = Text.assemble(
                (f"{e.index_status} ", f"bold {color}"), (e.path, theme.FG)
            )
            options.append(Option(text, id=e.path))  # id=路径，光标事件里靠它还原
            self._paths.append(e.path)
        if options:
            self.add_options(options)
        if self.highlighted is None and options:
            self.highlighted = 0  # 首次填充时让第一条获得高亮
        target = keep_path or self.highlighted_path
        if target in self._paths:
            try:
                idx = self.get_option_index(target)
            except Exception:
                idx = None
            if idx is not None:
                self.highlighted = idx

    @on(OptionList.OptionHighlighted)
    def _highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """光标移动到某选项时触发：记录路径，有焦点时通知 App 去加载 --cached diff。"""
        opt_id = event.option.id
        self.highlighted_path = str(opt_id) if opt_id is not None else None
        if self.highlighted_path and self.has_focus:
            self.post_message(FileHighlighted("staged", self.highlighted_path))

    def on_focus(self) -> None:
        """面板刚获得焦点时，让右侧 diff 同步到当前高亮的已暂存文件。"""
        if self.highlighted_path:
            self.post_message(FileHighlighted("staged", self.highlighted_path))

    # ---- actions --------------------------------------------------------
    def action_unstage(self) -> None:
        """Space：取消暂存当前高亮文件（restore --staged，工作区内容不动）。"""
        if self.highlighted_path:
            self.app.unstage_paths([self.highlighted_path])

    def action_stage_all(self) -> None:
        """a：全部暂存。"""
        self.app.stage_all()

    def action_unstage_all(self) -> None:
        """u：全部取消暂存。"""
        self.app.unstage_all()

    def action_edit(self) -> None:
        """e：用 $EDITOR 打开当前高亮文件。"""
        if self.highlighted_path:
            self.app.open_editor(self.highlighted_path)

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
        self.highlighted_path: str | None = None
        self._paths: list[str] = []

    def rebuild(self, st: RepoStatus, keep_path: str | None = None) -> None:
        self.clear_options()
        self._paths = []
        options: list[Option] = []
        for e in st.index_entries:
            color = theme.INDEX_COLORS.get(e.index_status, theme.FG)
            text = Text.assemble(
                (f"{e.index_status} ", f"bold {color}"), (e.path, theme.FG)
            )
            options.append(Option(text, id=e.path))
            self._paths.append(e.path)
        if options:
            self.add_options(options)
        if self.highlighted is None and options:
            self.highlighted = 0
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
        opt_id = event.option.id
        self.highlighted_path = str(opt_id) if opt_id is not None else None
        if self.highlighted_path and self.has_focus:
            self.post_message(FileHighlighted("staged", self.highlighted_path))

    def on_focus(self) -> None:
        if self.highlighted_path:
            self.post_message(FileHighlighted("staged", self.highlighted_path))

    # ---- actions --------------------------------------------------------
    def action_unstage(self) -> None:
        if self.highlighted_path:
            self.app.unstage_paths([self.highlighted_path])

    def action_stage_all(self) -> None:
        self.app.stage_all()

    def action_unstage_all(self) -> None:
        self.app.unstage_all()

    def action_edit(self) -> None:
        if self.highlighted_path:
            self.app.open_editor(self.highlighted_path)

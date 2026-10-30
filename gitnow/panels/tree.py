"""Left-top panel: file tree (worktree changes by default, toggleable to all files)."""

from __future__ import annotations

from rich.text import Text
from textual import on
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from .. import theme
from ..models import FileEntry, RepoStatus


class FileHighlighted(Message):
    """Cursor landed on a file in one of the left panels."""

    def __init__(self, panel: str, path: str) -> None:
        self.panel = panel
        self.path = path
        super().__init__()


class FileTreePanel(Tree):
    BINDINGS = [
        Binding("space", "stage_toggle", "暂存/取消", show=True),
        Binding("a", "stage_all", "全部暂存", show=False),
        Binding("u", "unstage_all", "全部取消", show=False),
        Binding("d", "discard", "丢弃", show=False),
        Binding("e", "edit", "编辑", show=False),
        Binding("t", "toggle_mode", "改动/全部", show=False),
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__("files", **kwargs)
        self.show_root = False
        self.mode = "changes"
        self.highlighted_path: str | None = None
        self._file_nodes: dict[str, TreeNode] = {}
        self._dir_nodes: list[TreeNode] = []

    @property
    def current_path(self) -> str | None:
        node = self.cursor_node
        if node is not None and node.data and node.data.get("path"):
            return node.data["path"]
        return self.highlighted_path

    def rebuild(
        self,
        st: RepoStatus,
        all_files: list[str],
        mode: str,
        keep_path: str | None,
    ) -> None:
        self.mode = mode
        self.clear()
        self._file_nodes = {}
        self._dir_nodes = []
        if mode == "changes":
            path_map = {e.path: e for e in st.entries if e.has_wt_changes}
        else:
            by_path = {e.path: e for e in st.entries}
            path_map = {p: by_path.get(p) for p in all_files}
        nested: dict = {}
        for path in sorted(path_map):
            parts = path.split("/")
            cursor = nested
            for part in parts[:-1]:
                cursor = cursor.setdefault(part + "/", {})
            cursor[parts[-1]] = path
        self._build_tree(self.root, nested, path_map)
        self.root.expand()
        for node in self._dir_nodes:
            node.expand()
        target = keep_path or self.highlighted_path
        if not (target and target in self._file_nodes):
            target = next(iter(self._file_nodes), None)
        if target and target in self._file_nodes:
            node = self._file_nodes[target]
            self.select_node(node)
            try:
                self.scroll_to_node(node, animate=False)
            except Exception:
                pass

    def _build_tree(self, parent_node: TreeNode, nested: dict, path_map: dict) -> None:
        for name in sorted(k for k in nested if k.endswith("/")):
            node = parent_node.add(
                Text(name.rstrip("/"), style=f"bold {theme.ACCENT_CYAN}"),
                data={"path": None},
            )
            self._dir_nodes.append(node)
            self._build_tree(node, nested[name], path_map)
        for name in sorted(k for k in nested if not k.endswith("/")):
            path = nested[name]
            node = parent_node.add(
                self._label(name, path_map.get(path)), data={"path": path}
            )
            self._file_nodes[path] = node

    def _label(self, name: str, entry: FileEntry | None) -> Text:
        if entry is None:
            return Text(name, style=theme.FG_DIM)
        if entry.unmerged:
            return Text.assemble(("UU ", f"bold {theme.BRIGHT_RED}"), (name, theme.FG))
        letter = entry.wt_letter
        color = theme.WT_COLORS.get(letter, theme.FG)
        return Text.assemble((f"{letter} ", f"bold {color}"), (name, theme.FG))

    @on(Tree.NodeHighlighted)
    def _node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        node = event.node
        data = node.data if node is not None else None
        if data and data.get("path"):
            self.highlighted_path = data["path"]
            if self.has_focus:
                self.post_message(FileHighlighted("tree", data["path"]))

    def on_focus(self) -> None:
        if self.highlighted_path:
            self.post_message(FileHighlighted("tree", self.highlighted_path))

    # ---- actions --------------------------------------------------------
    def _cursor_file(self) -> str | None:
        node = self.cursor_node
        if node is not None and node.data and node.data.get("path"):
            return node.data["path"]
        return None

    def action_stage_toggle(self) -> None:
        path = self._cursor_file()
        if path:
            self.app.stage_toggle("tree", path)

    def action_stage_all(self) -> None:
        self.app.stage_all()

    def action_unstage_all(self) -> None:
        self.app.unstage_all()

    def action_discard(self) -> None:
        path = self._cursor_file()
        if path:
            self.app.discard_request("tree", path)

    def action_edit(self) -> None:
        path = self._cursor_file()
        if path:
            self.app.open_editor(path)

    def action_toggle_mode(self) -> None:
        self.app.toggle_tree_mode()

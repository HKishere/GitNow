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
    """Cursor landed on a file in one of the left panels.

    由左侧任一面板（tree 或 staged）在光标落到某个文件上时发出，
    App 层接住后触发右侧 diff 加载。panel 字段标明来源（"tree"/"staged"），
    因为同一文件在两个面板里的 diff 类型不同（工作区 vs 已暂存）。
    """

    def __init__(self, panel: str, path: str) -> None:
        self.panel = panel  # 来源面板标识："tree" 或 "staged"
        self.path = path    # 仓库相对路径
        super().__init__()


class FileTreePanel(Tree):
    """左上角文件树。

    继承 Textual 的 Tree widget 获得展开/折叠、j/k 光标等交互；
    本类负责：把 RepoStatus 的文件列表按目录层级重建（rebuild）、
    给每行上色（_label）、把光标事件包装成 FileHighlighted 发给 App。

    两种显示模式（mode）：
      "changes" — 只显示工作区有改动的文件（默认）
      "all"     — 显示仓库全部文件（无改动的灰色），按 t 切换
    """

    BINDINGS = [
        Binding("space", "stage_toggle", "暂存/取消", show=True),
        Binding("a", "stage_all", "全部暂存", show=False),
        Binding("u", "unstage_all", "全部取消", show=False),
        Binding("d", "discard", "丢弃", show=False),
        Binding("e", "edit", "编辑", show=False),
        Binding("t", "toggle_mode", "改动/全部", show=False),
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
        Binding("left", "tree_left", show=False),
        Binding("h", "tree_left", show=False),
        Binding("right", "tree_right", show=False),
        Binding("l", "tree_right", show=False),
        Binding("f", "refresh_tree", "刷新树", show=True),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__("files", **kwargs)  # "files" 是根节点文字（被隐藏）
        self.show_root = False        # 隐藏树根，直接从顶层目录/文件开始
        self.mode = "changes"         # 当前模式，与 App.tree_mode 保持同步
        self.highlighted_path: str | None = None  # 最近一次光标停留的文件路径
        self._file_nodes: dict[str, TreeNode] = {}  # path -> 树节点，用于刷新后恢复光标
        self._dir_nodes: list[TreeNode] = []        # 所有目录节点，rebuild 后统一展开

    @property
    def current_path(self) -> str | None:
        """当前光标所在节点的文件路径。

        光标停在目录节点上时（目录 data.path=None），退回 highlighted_path
        ——最后一次光标停过的文件，让 App 层始终有"当前文件"可用。
        """
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
        """整体重建树。App 在每次 git 状态刷新后调用。

        流程：清空旧树 → 按 mode 选出要显示的文件集合 → 把扁平路径列表
        组装成嵌套 dict（目录 -> 子内容）→ 递归挂到树上 → 全部展开 →
        尽量把光标恢复到刷新前的文件上（keep_path），否则落到第一个文件。

        - mode="changes" 时 path_map = {path: FileEntry}，只含工作区有改动的文件
        - mode="all" 时 path_map 覆盖全部文件；status 里没有的文件（无改动）
          映射为 None entry，渲染成灰色
        - nested 的结构形如：
            {"src/": {"main.py": "src/main.py"}, "README.md": "README.md"}
          叶子值是完整路径，目录键以 "/" 结尾以便和文件区分
        """
        self.mode = mode
        self.clear()  # 清掉所有节点（Tree.clear 只留根）
        self._file_nodes = {}
        self._dir_nodes = []
        if mode == "changes":
            path_map = {e.path: e for e in st.entries if e.has_wt_changes}
        else:
            by_path = {e.path: e for e in st.entries}
            path_map = {p: by_path.get(p) for p in all_files}
        # 把 "a/b/c.py" 这样的扁平路径塞进嵌套 dict，形成目录层级
        nested: dict = {}
        for path in sorted(path_map):
            parts = path.split("/")
            cursor = nested
            for part in parts[:-1]:  # 前 n-1 段是目录，键加 "/" 标记
                cursor = cursor.setdefault(part + "/", {})
            cursor[parts[-1]] = path  # 最后一段是文件，值为完整路径
        self._build_tree(self.root, nested, path_map)
        self.root.expand()
        for node in self._dir_nodes:
            node.expand()  # 默认全部展开，不用逐个点开
        # 恢复光标位置：优先 keep_path（App 传来的上次路径），
        # 失效了（文件已无改动被移除）就退回 highlighted_path，再不行选第一个文件
        target = keep_path or self.highlighted_path
        if not (target and target in self._file_nodes):
            target = next(iter(self._file_nodes), None)
        if target and target in self._file_nodes:
            node = self._file_nodes[target]
            self.select_node(node)
            try:
                self.scroll_to_node(node, animate=False)
            except Exception:
                pass  # 节点尚未布局时 scroll 会失败，忽略即可

    def _build_tree(self, parent_node: TreeNode, nested: dict, path_map: dict) -> None:
        """递归把嵌套 dict 挂到树上。

        先加目录（键以 "/" 结尾，排序保证目录在文件前），再递归其子层；
        然后加文件叶子。目录节点 data.path=None（光标停在目录上不算选中文件），
        文件节点 data.path=完整路径 且 allow_expand=False——叶子不渲染展开三角，
        按 Enter 也不会试图展开。
        """
        for name in sorted(k for k in nested if k.endswith("/")):
            node = parent_node.add(
                Text(name.rstrip("/"), style=f"bold {theme.ACCENT_CYAN}"),  # 目录名：青色加粗
                data={"path": None},
            )
            self._dir_nodes.append(node)
            self._build_tree(node, nested[name], path_map)
        for name in sorted(k for k in nested if not k.endswith("/")):
            path = nested[name]
            node = parent_node.add(
                self._label(name, path_map.get(path)),
                data={"path": path},
                allow_expand=False,
            )
            self._file_nodes[path] = node

    def _label(self, name: str, entry: FileEntry | None) -> Text:
        """生成文件节点显示用的 rich Text（状态前缀字母 + 文件名）。

        - entry 为 None：无改动的普通文件 → 整行暗灰
        - 冲突文件 → 亮红 "UU" 前缀
        - 其余 → 按工作区状态字母查 WT_COLORS 上色（M 橙 / D 红 / ? 蓝 / A 绿…）
        """
        if entry is None:
            return Text(name, style=theme.FG_DIM)
        if entry.unmerged:
            return Text.assemble(("UU ", f"bold {theme.BRIGHT_RED}"), (name, theme.FG))
        letter = entry.wt_letter
        color = theme.WT_COLORS.get(letter, theme.FG)
        return Text.assemble((f"{letter} ", f"bold {color}"), (name, theme.FG))

    @on(Tree.NodeHighlighted)
    def _node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        """光标移动到某节点时触发（j/k/鼠标都在内）。

        记录 highlighted_path；仅当本面板拥有焦点时才向 App 发 FileHighlighted
        ——否则后台自动刷新重建树引发的"光标复位"也会触发右侧 diff 重载。
        """
        node = event.node
        data = node.data if node is not None else None
        if data and data.get("path"):
            self.highlighted_path = data["path"]
            if self.has_focus:
                self.post_message(FileHighlighted("tree", data["path"]))

    def on_focus(self) -> None:
        """面板刚获得焦点（如 Tab 切换过来）时，立刻让右侧 diff 同步到当前文件。"""
        if self.highlighted_path:
            self.post_message(FileHighlighted("tree", self.highlighted_path))

    # ---- actions --------------------------------------------------------
    def _cursor_file(self) -> str | None:
        """光标所在节点的文件路径；目录节点返回 None（操作只对文件生效）。"""
        node = self.cursor_node
        if node is not None and node.data and node.data.get("path"):
            return node.data["path"]
        return None

    def _cursor_dir(self) -> TreeNode | None:
        """光标所在节点的目录 TreeNode；光标在文件或根上时返回 None。

        目录节点的特征是 allow_expand=True（文件叶子建节点时传了
        allow_expand=False），且不是被隐藏的根节点。
        """
        node = self.cursor_node
        if node is not None and node.allow_expand and node is not self.root:
            return node
        return None

    def action_tree_left(self) -> None:
        """h / ←：光标停在文件夹上时折叠它（已折叠则保持不动）；
        光标在文件等其他位置时退回全局行为——切换面板（向左）。"""
        node = self._cursor_dir()
        if node is not None:
            node.collapse()
        else:
            self.app.action_cycle_focus_back()

    def action_tree_right(self) -> None:
        """l / →：光标停在文件夹上时展开它（已展开则保持不动）；
        光标在文件等其他位置时退回全局行为——切换面板（向右）。"""
        node = self._cursor_dir()
        if node is not None:
            node.expand()
        else:
            self.app.action_cycle_focus()

    def action_stage_toggle(self) -> None:
        """Space：暂存光标文件（若已暂存则取消，方向判断在 App.stage_toggle）。"""
        path = self._cursor_file()
        if path:
            self.app.stage_toggle("tree", path)

    def action_stage_all(self) -> None:
        """a：全部暂存（委托给 App 统一走 _mutate 后台管线）。"""
        self.app.stage_all()

    def action_unstage_all(self) -> None:
        """u：全部取消暂存。"""
        self.app.unstage_all()

    def action_discard(self) -> None:
        """d：丢弃光标文件的工作区改动（App 层会先弹确认框，不可撤销）。"""
        path = self._cursor_file()
        if path:
            self.app.discard_request("tree", path)

    def action_edit(self) -> None:
        """e：用 $EDITOR 打开光标文件。"""
        path = self._cursor_file()
        if path:
            self.app.open_editor(path)

    def action_toggle_mode(self) -> None:
        """t：在"仅改动"和"全部文件"两种树模式间切换。"""
        self.app.toggle_tree_mode()

    def action_refresh_tree(self) -> None:
        """f：手动刷新。走 App.refresh_all()（后台线程 + exclusive），
        会重拉 git 状态并重建树、状态栏和已暂存面板，还能保留光标位置。"""
        self.app.refresh_all()

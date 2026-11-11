"""Data models shared across GitNow."""

from __future__ import annotations

from dataclasses import dataclass, field

# git status --porcelain=v2 中表示"合并冲突"的 XY 状态组合全集。
# 例如 UU = 双方都修改、AU = 我方新增对方删除（added by us）。
# 只要 xy 落在这个集合里，UI 就按"冲突"样式（红色 UU 前缀）渲染。
CONFLICT_XY = {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}


@dataclass
class FileEntry:
    """One path as reported by `git status --porcelain=v2`.

    xy is the 2-char XY code: index status + worktree status,
    '.' means no change, '??' means untracked, 'UU' etc. means conflict.
    """

    path: str                # 仓库相对路径（重命名时是新路径）
    xy: str = ".."           # 两位状态码：第一位暂存区(X)、第二位工作区(Y)
    renamed_from: str | None = None  # 重命名/拷贝时的原路径（porcelain v2 的 "2 " 记录会额外跟一行）

    def __post_init__(self) -> None:
        # porcelain v2 用空格表示"无改动"（如 "M " 或 " M"），
        # 统一替换成 '.'，这样 xy 永远是两个可见字符，后续判断和显示都更简单。
        self.xy = (self.xy or "..").replace(" ", ".")

    @property
    def untracked(self) -> bool:
        """未跟踪文件（porcelain 输出为独立的 "? " 记录，xy 固定为 ??）。"""
        return self.xy == "??"

    @property
    def unmerged(self) -> bool:
        """是否处于合并冲突状态（xy 落在冲突码集合里，如 UU/AU/DU）。"""
        return self.xy in CONFLICT_XY

    @property
    def index_status(self) -> str:
        """暂存区状态字母（xy 第一位）：A 新增 / M 修改 / D 删除 / R 重命名。"""
        return self.xy[0]

    @property
    def wt_status(self) -> str:
        """工作区状态字母（xy 第二位）：M 修改 / D 删除 / T 类型变更。"""
        return self.xy[1]

    @property
    def has_index_changes(self) -> bool:
        """暂存区是否有改动（未跟踪文件不算——它根本不在 index 里）。"""
        return not self.untracked and self.xy[0] != "."

    @property
    def has_wt_changes(self) -> bool:
        """工作区是否有改动（未跟踪文件也算工作区改动，因为它整个文件都是"新"的）。"""
        return self.untracked or self.xy[1] != "."

    @property
    def wt_letter(self) -> str:
        """文件树里显示的工作区前缀字母：未跟踪显示 ?，其余直接用状态字母。"""
        return "?" if self.untracked else self.wt_status

    @property
    def index_letter(self) -> str:
        """已暂存面板显示的前缀字母：未跟踪（被 add 过）显示 A（新增），其余用暂存区字母。"""
        return "A" if self.untracked else self.index_status


@dataclass
class LogEntry:
    """一条 git log 记录，字段与 gitbackend.LOG_FORMAT 的列一一对应。"""

    sha: str        # 完整 40 位 SHA（用作 OptionList 的 option id）
    short: str      # 短 SHA（log 列表里显示 7 位）
    author: str     # 作者名
    date: str       # 格式化后的日期字符串（DATE_FORMAT）
    subject: str    # 提交说明第一行
    refs: str = ""  # 该提交指向的引用（如 "HEAD -> master, origin/master"），无则为空


@dataclass
class RepoStatus:
    """一次 `git status --porcelain=v2 --branch` 解析出的完整仓库状态快照。"""

    head: str = ""                 # 当前分支名；detached HEAD 时为 "(detached)"
    head_detached: bool = False    # 是否处于游离 HEAD 状态（状态栏用橙色显示）
    head_oid: str = ""             # 当前 HEAD 的完整 SHA；空仓库为 "(initial)"
    upstream: str | None = None    # 上游分支名（如 "origin/master"），没有则为 None
    ahead: int = 0                 # 本地领先上游的提交数（状态栏 ↑N）
    behind: int = 0                # 本地落后上游的提交数（状态栏 ↓N）
    has_commits: bool = True       # 仓库是否已有提交（决定 push/reset 等操作能不能做）
    entries: list[FileEntry] = field(default_factory=list)  # 所有有变化的文件

    def entry(self, path: str) -> FileEntry | None:
        """按路径查找文件条目；找不到（比如刷新后文件已无改动）返回 None。"""
        for e in self.entries:
            if e.path == path:
                return e
        return None

    @property
    def worktree_entries(self) -> list[FileEntry]:
        """工作区有改动的文件列表（文件树默认模式 / 状态栏"改动"计数）。"""
        return [e for e in self.entries if e.has_wt_changes]

    @property
    def index_entries(self) -> list[FileEntry]:
        """暂存区有改动的文件列表（已暂存面板 / 状态栏"已暂存"计数）。"""
        return [e for e in self.entries if e.has_index_changes]

    @property
    def signature(self) -> str:
        """把整个状态压成一个字符串指纹（分支+ahead/behind+每个文件的 xy:path）。

        可用于对比两次刷新之间状态是否真的变了，避免无意义的 UI 重建。
        """
        parts = [self.head, str(self.ahead), str(self.behind)]
        parts += [f"{e.xy}:{e.path}" for e in self.entries]
        return "|".join(parts)

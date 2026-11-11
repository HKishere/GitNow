"""Keymap tables - single source used by both the status bar and the help modal.

所有 (按键, 说明) 表集中在这里定义：HelpModal 用 all_sections() 展示完整表，
StatusBar 用 STATUS_BAR_KEYS 展示精简版。改快捷键说明只需要改这一个文件。
"""

# 全局按键（App 层 BINDINGS，任何面板获得焦点时都生效）
GLOBAL_KEYS = [
    ("Tab/h/l", "切换面板"),
    ("t", "树: 改动↔全部"),
    ("r", "刷新"),
    ("Esc", "取消选中→log"),
    ("c", "提交"),
    ("P", "push"),
    ("p", "pull"),
    ("f", "fetch"),
    ("?", "帮助"),
    ("q", "退出"),
]

# 文件区按键（文件树 / 已暂存面板获得焦点时生效）
FILE_KEYS = [
    ("↑↓/j k", "移动"),
    ("←→/h l", "折叠/展开文件夹(文件树)"),
    ("Space", "暂存/取消暂存"),
    ("a", "全部暂存"),
    ("u", "全部取消暂存"),
    ("d", "丢弃改动(需确认)"),
    ("e", "编辑器打开"),
]

# 右侧区域按键（log 列表 / diff / commit 详情）
RIGHT_KEYS = [
    ("j k/PgUp/PgDn", "滚动或移动"),
    ("Enter", "查看提交详情(log 内)"),
    ("Esc", "返回 / 取消选中"),
]

# 提交弹窗（CommitModal）
COMMIT_KEYS = [
    ("Ctrl+S", "提交"),
    ("Esc", "取消"),
]

# 确认弹窗（ConfirmModal，如丢弃改动）
CONFIRM_KEYS = [
    ("y", "确认"),
    ("n/Esc", "取消"),
]


def all_sections() -> list[tuple[str, list[tuple[str, str]]]]:
    """返回 (分区标题, 按键表) 的完整清单，供 HelpModal 逐节渲染。"""
    return [
        ("全局", GLOBAL_KEYS),
        ("文件区 (文件树 / 已暂存)", FILE_KEYS),
        ("右侧 (log / diff)", RIGHT_KEYS),
        ("提交弹窗", COMMIT_KEYS),
        ("确认弹窗", CONFIRM_KEYS),
    ]


# compact subset shown in the status bar (full table lives in the help modal)
# 状态栏只放最常用的 8 个，完整表在帮助弹窗里（? 键查看）
STATUS_BAR_KEYS = [
    ("Tab", "切换"),
    ("Space", "暂存"),
    ("c", "提交"),
    ("P", "push"),
    ("p", "pull"),
    ("f", "fetch"),
    ("t", "全部"),
    ("?", "帮助"),
    ("q", "退出"),
]

# 按聚焦面板区分的状态栏右下角提示（App 在焦点变化时切换）。
# 键集是各面板 BINDINGS 的精选子集——状态栏一行放不下完整表，只挑该
# 上下文里最常用的操作；找不到上下文时退回 STATUS_BAR_KEYS。
CONTEXT_STATUS_KEYS: dict[str, list[tuple[str, str]]] = {
    "tree": [
        ("Tab", "切换面板"),
        ("Space", "暂存"),
        ("a", "全部暂存"),
        ("d", "丢弃"),
        ("t", "改动↔全部"),
        ("h/l", "折叠/展开"),
        ("?", "帮助"),
        ("q", "退出"),
    ],
    "staged": [
        ("Tab", "切换面板"),
        ("Space", "取消暂存"),
        ("a", "全部暂存"),
        ("u", "全部取消"),
        ("e", "编辑"),
        ("?", "帮助"),
        ("q", "退出"),
    ],
    "log": [
        ("Tab", "切换面板"),
        ("↑↓/j k", "选择"),
        ("Enter", "提交详情"),
        ("Esc", "取消选中"),
        ("?", "帮助"),
        ("q", "退出"),
    ],
    "diff": [
        ("Tab", "切换面板"),
        ("j k/PgUp/PgDn", "滚动"),
        ("Esc", "返回 log"),
        ("?", "帮助"),
        ("q", "退出"),
    ],
}


def status_keys(context: str | None) -> list[tuple[str, str]]:
    """返回指定面板上下文的状态栏提示；未知上下文用全局默认表。"""
    return CONTEXT_STATUS_KEYS.get(context or "", STATUS_BAR_KEYS)

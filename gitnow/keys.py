"""Keymap tables - single source used by both the status bar and the help modal."""

GLOBAL_KEYS = [
    ("Tab/h/l", "切换面板"),
    ("t", "树: 改动↔全部"),
    ("r", "刷新"),
    ("Esc", "取消选中→log"),
    ("c", "提交"),
    ("P", "push"),
    ("p", "pull"),
    ("?", "帮助"),
    ("q", "退出"),
]

FILE_KEYS = [
    ("↑↓/j k", "移动"),
    ("Space", "暂存/取消暂存"),
    ("a", "全部暂存"),
    ("u", "全部取消暂存"),
    ("d", "丢弃改动(需确认)"),
    ("e", "编辑器打开"),
]

RIGHT_KEYS = [
    ("j k/PgUp/PgDn", "滚动或移动"),
    ("Enter", "查看提交详情(log 内)"),
    ("Esc", "返回 / 取消选中"),
]

COMMIT_KEYS = [
    ("Ctrl+S", "提交"),
    ("Esc", "取消"),
]

CONFIRM_KEYS = [
    ("y", "确认"),
    ("n/Esc", "取消"),
]


def all_sections() -> list[tuple[str, list[tuple[str, str]]]]:
    return [
        ("全局", GLOBAL_KEYS),
        ("文件区 (文件树 / 已暂存)", FILE_KEYS),
        ("右侧 (log / diff)", RIGHT_KEYS),
        ("提交弹窗", COMMIT_KEYS),
        ("确认弹窗", CONFIRM_KEYS),
    ]


# compact subset shown in the status bar (full table lives in the help modal)
STATUS_BAR_KEYS = [
    ("Tab", "切换"),
    ("Space", "暂存"),
    ("c", "提交"),
    ("P", "push"),
    ("p", "pull"),
    ("t", "全部"),
    ("?", "帮助"),
    ("q", "退出"),
]

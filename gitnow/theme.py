"""Shared color constants for python-rendered rich Text (theme blocks live in gitnow.tcss)."""

FG = "#c0caf5"
FG_DIM = "#565f89"
ACCENT_BLUE = "#7aa2f7"
ACCENT_GREEN = "#9ece6a"
ACCENT_ORANGE = "#e0af68"
ACCENT_RED = "#f7768e"
ACCENT_PURPLE = "#bb9af7"
ACCENT_CYAN = "#7dcfff"
BRIGHT_RED = "#ff5555"

# worktree status letter -> color (file tree panel)
WT_COLORS = {
    "M": ACCENT_ORANGE,
    "D": ACCENT_RED,
    "?": ACCENT_BLUE,
    "A": ACCENT_GREEN,
    "R": ACCENT_PURPLE,
    "C": ACCENT_PURPLE,
    "T": ACCENT_PURPLE,
}

# index status letter -> color (staged panel, gitui-style green family)
INDEX_COLORS = {
    "A": ACCENT_GREEN,
    "M": ACCENT_GREEN,
    "D": ACCENT_RED,
    "R": ACCENT_PURPLE,
    "C": ACCENT_PURPLE,
    "U": BRIGHT_RED,
}

DIFF_STYLES = {
    "meta": f"bold {ACCENT_BLUE}",
    "hunk": ACCENT_PURPLE,
    "add": f"{ACCENT_GREEN} on #12281a",
    "del": f"{ACCENT_RED} on #2a1418",
    "range": f"dim {FG_DIM}",
}

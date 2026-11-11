"""Shared color constants for python-rendered rich Text (theme blocks live in gitnow.tcss)."""

# Tokyo Night 配色。所有由 Python 侧 rich Text 使用的颜色都收拢在此，
# tcss 里布局用的颜色在 gitnow.tcss 中另行定义，两处需保持视觉一致。

FG = "#c0caf5"           # 普通前景色（文件名、正文）
FG_DIM = "#565f89"       # 弱化色（无改动文件、日期、提示文字）
ACCENT_BLUE = "#7aa2f7"   # 未跟踪文件 / diff 元信息 / 聚焦边框
ACCENT_GREEN = "#9ece6a"  # 新增(A) / 已暂存 / 分支名
ACCENT_ORANGE = "#e0af68" # 修改(M) / 短 SHA / 聚焦边框
ACCENT_RED = "#f7768e"    # 删除(D) / diff 删除行
ACCENT_PURPLE = "#bb9af7" # 重命名(R)/拷贝(C)/类型变更(T) / diff hunk 头
ACCENT_CYAN = "#7dcfff"   # 目录名 / log 作者
BRIGHT_RED = "#ff5555"    # 合并冲突(UU)专用，比 ACCENT_RED 更刺眼

# 工作区状态字母 -> 颜色（文件树面板的前缀字母）
WT_COLORS = {
    "M": ACCENT_ORANGE,   # 修改
    "D": ACCENT_RED,      # 删除
    "?": ACCENT_BLUE,     # 未跟踪
    "A": ACCENT_GREEN,    # 新增
    "R": ACCENT_PURPLE,   # 重命名
    "C": ACCENT_PURPLE,   # 拷贝
    "T": ACCENT_PURPLE,   # 类型变更（如符号链接 <-> 普通文件）
}

# 暂存区状态字母 -> 颜色（已暂存面板，gitui 风格的绿色系）
INDEX_COLORS = {
    "A": ACCENT_GREEN,    # 新增
    "M": ACCENT_GREEN,    # 修改
    "D": ACCENT_RED,      # 删除
    "R": ACCENT_PURPLE,   # 重命名
    "C": ACCENT_PURPLE,   # 拷贝
    "U": BRIGHT_RED,      # 冲突（unmerged）
}

# diff 渲染样式表（viewer._append_diff 按行前缀查表上色）
DIFF_STYLES = {
    "meta": f"bold {ACCENT_BLUE}",      # "diff --git a/x b/x" 行
    "hunk": ACCENT_PURPLE,               # "@@ -1,3 +1,4 @@" hunk 头
    "add": f"{ACCENT_GREEN} on #12281a", # "+" 新增行（绿色字+深绿底）
    "del": f"{ACCENT_RED} on #2a1418",   # "-" 删除行（红色字+深红底）
    "range": f"dim {FG_DIM}",            # ---/+++/index 等范围行
}

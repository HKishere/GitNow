"""GitNow application: layout, focus routing, all actions."""

from __future__ import annotations

from functools import partial
from pathlib import Path

from rich.text import Text as RichText
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical

from . import gitbackend, keys, theme
from .gitbackend import GitError
from .models import LogEntry, RepoStatus
from .panels.modals import CommitModal, ConfirmModal, HelpModal
from .panels.staged import StagedPanel
from .panels.statusbar import StatusBar
from .panels.tree import FileHighlighted, FileTreePanel
from .panels.viewer import BackRequested, CommitRequested, LogNearEnd, RightViewer


class GitNowApp(App):
    """GitNow 主应用：组合所有面板、分发消息、调度后台 git 操作。

    职责划分：子面板只发 Message 汇报事件（光标移动/按键意图），
    所有涉及仓库状态的业务逻辑和后台线程调度都在这一层。
    """

    TITLE = "GitNow"
    CSS_PATH = "gitnow.tcss"  # 布局与配色在 tcss 里定义

    BINDINGS = [
        Binding("tab", "cycle_focus", "切换面板", show=False),
        Binding("l", "cycle_focus", show=False),
        Binding("h", "cycle_focus_back", show=False),
        Binding("t", "toggle_tree_mode", "树模式", show=False),
        Binding("r", "refresh", "刷新", show=False),
        Binding("c", "commit", "提交", show=False),
        Binding("P", "push", "push", show=False),
        Binding("p", "pull", "pull", show=False),
        Binding("a", "stage_all", show=False),
        Binding("u", "unstage_all", show=False),
        Binding("question_mark", "help", "帮助", show=False),
        Binding("escape", "clear_selection", show=False),
        Binding("q", "quit", "退出", show=False),
    ]

    def __init__(self, repo_path: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.repo_path = repo_path      # 仓库绝对路径（所有 gitbackend 调用都用它）
        self.status: RepoStatus | None = None      # 最近一次 status 快照
        self.selected: tuple[str, str] | None = None  # 当前选中 (来源面板, 文件路径)
        self.tree_mode = "changes"      # 文件树模式："changes" 仅改动 / "all" 全部文件
        self.log_entries: list[LogEntry] = []  # 已加载的全部 log 条目（分页累积）
        self.log_complete = False       # log 是否已经全部加载完
        self._busy = 0                  # 进行中的写操作计数（>0 时状态栏显示 … 并暂停自动刷新）
        self._log_loading = False       # 是否有一页 log 正在加载（防重复请求）
        self._all_files: list[str] = [] # "全部文件"模式下缓存的文件清单

    # ---- widgets ----------------------------------------------------------
    def compose(self) -> ComposeResult:
        """整体布局：左侧（文件树 + 已暂存）| 右侧查看器，底部状态栏。"""
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield FileTreePanel(id="tree-panel")
                yield StagedPanel(id="staged-panel")
            yield RightViewer(id="viewer")
        yield StatusBar(id="statusbar")

    @property
    def tree_panel(self) -> FileTreePanel:
        """左侧文件树（query_one 的缓存式封装，调用方免写选择器）。"""
        return self.query_one("#tree-panel", FileTreePanel)

    @property
    def staged_panel(self) -> StagedPanel:
        """左下已暂存面板。"""
        return self.query_one("#staged-panel", StagedPanel)

    @property
    def viewer(self) -> RightViewer:
        """右侧查看器（log/diff/commit）。"""
        return self.query_one("#viewer", RightViewer)

    @property
    def status_bar(self) -> StatusBar:
        """底部状态栏。"""
        return self.query_one("#statusbar", StatusBar)

    @property
    def focus_targets(self) -> list:
        """Tab 循环聚焦的目标面板列表（按 Tab 顺序）。

        viewer 处于 log 模式时聚焦到内部的 log 列表（它才是可滚动/可
        高亮的组件），diff/commit 模式则聚焦 viewer 本身。
        """
        viewer = self.viewer.log_list if self.viewer.mode == "log" else self.viewer
        return [self.tree_panel, self.staged_panel, viewer]

    # ---- lifecycle ----------------------------------------------------------
    def on_mount(self) -> None:
        """挂载完成：设置面板标题 → 首次加载状态和 log → 启动定时器 → 聚焦文件树。

        set_interval(3.0, ...) 每 3 秒自动刷新一次 git 状态，
        让外部（终端/其他工具）做的 git 操作也能反映到界面上。
        """
        # 面板标题用带样式的 RichText，tcss 只管边框颜色
        self.tree_panel.border_title = RichText(" 文件树 ", style=f"bold {theme.ACCENT_BLUE}")
        self.staged_panel.border_title = RichText(" 已暂存 (staged) ", style=f"bold {theme.ACCENT_GREEN}")
        self.viewer.border_title = RichText(" log / diff ", style=f"bold {theme.ACCENT_ORANGE}")
        self.viewer.show_note("加载中…")  # 占位，log 后台加载完成后自动替换
        self.status_bar.update_status(RepoStatus(head="…"))  # 占位状态
        self.refresh_all()
        self.load_log()
        self.set_interval(3.0, self._auto_refresh)
        self.set_focus(self.tree_panel)

    def _auto_refresh(self) -> None:
        """定时自动刷新入口。有写操作进行中（_busy）或弹窗打开（screen 栈 >1）时跳过，
        避免与手动操作/弹窗互相踩（比如提交到一半列表被重建）。"""
        if self._busy or len(self.screen_stack) > 1:
            return
        self.refresh_all()

    # ---- refresh ----------------------------------------------------------
    @work(thread=True, group="refresh", exclusive=True)
    def refresh_all(self) -> None:
        """后台刷新仓库状态（git status 是子进程调用，绝不能在 UI 线程跑）。

        - thread=True：丢线程池；exclusive=True：同组上一次没跑完就取消，
          防止 3 秒定时器和手动刷新堆积出多个并发 git status
        - "全部文件"模式额外调 list_all_files（也是一次 git 子进程）
        - 出错用 notify 弹 toast；成功后通过 call_from_thread 回到主线程
          执行 _apply_status 更新 UI（后台线程不能直接碰 widget）
        """
        try:
            st = gitbackend.status(self.repo_path)
            all_files = (
                gitbackend.list_all_files(self.repo_path)
                if self.tree_mode == "all"
                else []
            )
        except Exception as e:  # noqa: BLE001 - surface any git failure
            self.call_from_thread(self.notify, f"git 出错: {e}", severity="error")
            return
        self.call_from_thread(self._apply_status, st, all_files)

    def _apply_status(self, st: RepoStatus, all_files: list[str]) -> None:
        """把新的 status 快照应用到所有面板（主线程执行）。

        同时做"选中失效清理"：当前选中的文件如果已无改动（比如刚被提交/恢复），
        取消选中并把 viewer 退回 log 视图，避免右侧悬挂着一个过期 diff。
        """
        self.status = st
        if all_files:
            self._all_files = all_files  # 只在非空时更新，"changes" 模式传空列表不能覆盖缓存
        self.status_bar.update_status(st, busy=self._busy > 0)
        self.tree_panel.rebuild(
            st, self._all_files, self.tree_mode, keep_path=self.tree_panel.current_path
        )
        self.staged_panel.rebuild(st, keep_path=self.staged_panel.highlighted_path)
        if self.selected:
            entry = st.entry(self.selected[1])
            # 选中项已无任何改动 → 取消选中，清掉 viewer 的 token
            if entry is None or not (entry.has_index_changes or entry.has_wt_changes):
                self.selected = None
                self.viewer.token = None
        if self.selected is None and self.viewer.mode == "diff":
            # 之前在看 diff 但选中已失效 → 退回 log 列表
            self.viewer.populate_log(self.log_entries, self.log_complete)

    # ---- log ----------------------------------------------------------
    @work(thread=True, group="log", exclusive=True)
    def load_log(self, append: bool = False) -> None:
        """后台加载一页 git log。

        append=False：从头加载（初始/刷新/写操作后）；append=True：无限滚动
        翻页，skip=已加载条数。出错静默返回空列表（log 加载失败不该打扰用户，
        界面仍可用）。
        """
        skip = len(self.log_entries) if append else 0
        try:
            entries = gitbackend.log(self.repo_path, skip=skip)
        except Exception:  # noqa: BLE001
            entries = []
        self.call_from_thread(self._apply_log, entries, append)

    def _apply_log(self, entries: list[LogEntry], append: bool) -> None:
        """把新加载的一页 log 合并进缓存并刷新 viewer（主线程执行）。"""
        self._log_loading = False
        if not append:
            self.log_entries = []  # 从头加载：先清缓存
        self.log_entries.extend(entries)
        # 返回条数 < 每页上限说明已经到底了
        self.log_complete = len(entries) < gitbackend.LOG_PAGE
        if self.viewer.mode == "log" or (
            self.selected is None and self.viewer.mode != "commit"
        ):
            # 仅当 viewer 正在看 log（或空闲）才重建列表；
            # 用户正在看 diff/commit 时静默更新缓存，不抢屏
            self.viewer.populate_log(self.log_entries, self.log_complete)

    def load_more_log(self) -> None:
        """请求加载下一页 log（由 LogNearEnd 消息触发）。

        三个卫语句：已全部加载 / 已有加载在进行 / viewer 不在 log 模式，
        都直接返回，避免重复请求或无效请求。
        """
        if self.log_complete or self._log_loading or self.viewer.mode != "log":
            return
        self._log_loading = True
        self.load_log(append=True)

    # ---- selection / diff ------------------------------------------------
    @on(FileHighlighted)
    def on_file_highlighted(self, event: FileHighlighted) -> None:
        """文件树/已暂存面板的光标移动事件 → 更新选中并加载对应 diff。"""
        self.set_selection(event.panel, event.path)

    def set_selection(self, panel: str, path: str) -> None:
        """记录当前选中（来源面板 + 路径），设置 viewer 的 token 并请求 diff。

        token=(panel, path)：后台 diff 加载完成回填时，viewer 用它校验
        用户是否已经切走了（切走了就丢弃结果）。选中的是同一个文件时直接返回，
        避免重复请求。
        """
        if self.selected == (panel, path):
            return
        self.selected = (panel, path)
        self.viewer.token = (panel, path)
        self.request_diff()

    @work(thread=True, group="diff", exclusive=True)
    def request_diff(self) -> None:
        """后台加载当前选中文件的 diff，自动区分三种来源：

        - 选中自 staged 面板，或文件只有暂存区改动 → diff --cached（"已暂存"）
        - 未跟踪文件 → 与 /dev/null 比较的 diff（"未跟踪"）
        - 其余 → 工作区 vs 暂存区 diff（"工作区"）
        结果经 call_from_thread 回主线程，viewer 用 token 决定是否采纳。
        """
        if not self.selected or not self.status:
            return
        src, path = self.selected
        entry = self.status.entry(path)
        if entry is None:
            return
        if src == "staged" or (not entry.has_wt_changes and entry.has_index_changes):
            text = gitbackend.diff_cached(self.repo_path, path)
            badge = "已暂存"
        elif entry.untracked:
            text = gitbackend.diff_untracked(self.repo_path, path)
            badge = "未跟踪"
        else:
            text = gitbackend.diff_worktree(self.repo_path, path)
            badge = "工作区"
        self.call_from_thread(self.viewer.apply_diff, path, badge, text, (src, path))

    @on(CommitRequested)
    def on_commit_requested(self, event: CommitRequested) -> None:
        """log 列表按 Enter → 请求查看该提交详情。只在 log 模式响应。"""
        if self.viewer.mode != "log":
            return
        self.viewer.token = ("commit", event.sha)  # 新 token，作废之前未完成的 diff
        self._fetch_commit(event.sha)

    @work(thread=True, group="diff", exclusive=True)
    def _fetch_commit(self, sha: str) -> None:
        """后台执行 git show 拉取提交详情；show 失败把 stderr 显示在页面里而不是崩溃。"""
        try:
            text = gitbackend.show_commit(self.repo_path, sha)
        except GitError as e:
            text = f"(show 失败: {e.stderr})"
        self.call_from_thread(self.viewer.apply_commit, sha, text, ("commit", sha))

    @on(BackRequested)
    def _on_back(self, event: BackRequested) -> None:
        """viewer 的 Esc：commit 视图退回 log；diff 视图相当于取消选中。"""
        if self.viewer.mode == "commit":
            self._back_to_log()
        else:
            self.clear_selection()

    @on(LogNearEnd)
    def _on_log_near_end(self, event: LogNearEnd) -> None:
        """log 滚到末尾附近 → 加载下一页。"""
        self.load_more_log()

    def action_clear_selection(self) -> None:
        """全局 Esc：弹窗打开时不响应；否则按 viewer 所处视图返回/取消选中。"""
        if len(self.screen_stack) > 1:
            return
        if self.viewer.mode == "commit":
            self._back_to_log()
        else:
            self.clear_selection()

    def _back_to_log(self) -> None:
        """从 commit 详情视图退回 log 列表（清 token，重建列表，聚焦列表）。"""
        self.viewer.token = None
        self.viewer.populate_log(self.log_entries, self.log_complete)
        self._focus_log_list()

    def clear_selection(self) -> None:
        """取消文件选中并回到 log 视图。"""
        self.selected = None
        self.viewer.token = None
        self.viewer.populate_log(self.log_entries, self.log_complete)
        self._focus_log_list()

    def _focus_log_list(self) -> None:
        """让 log 列表获得焦点（仅在它可见且未持有时），Esc 后用户可以直接继续翻 log。"""
        log_list = self.viewer.log_list
        if log_list.display and not log_list.has_focus:
            log_list.focus()

    # ---- focus ----------------------------------------------------------
    def action_cycle_focus(self) -> None:
        """Tab/l：在 文件树 → 已暂存 → viewer 之间循环聚焦。弹窗打开时不响应。"""
        if len(self.screen_stack) > 1:
            return
        targets = self.focus_targets
        try:
            idx = targets.index(self.focused)
        except ValueError:
            idx = -1  # 当前焦点不在目标列表里（如弹窗关闭后），从头开始
        targets[(idx + 1) % len(targets)].focus()

    def action_cycle_focus_back(self) -> None:
        """h：反向循环聚焦。"""
        if len(self.screen_stack) > 1:
            return
        targets = self.focus_targets
        try:
            idx = targets.index(self.focused)
        except ValueError:
            idx = 0
        targets[(idx - 1) % len(targets)].focus()

    # ---- stage ops ----------------------------------------------------------
    def stage_toggle(self, src: str, path: str) -> None:
        """Space 的方向判断：在 staged 面板里 = 取消暂存；
        在文件树里看状态——工作区有改动 → 暂存，只有暂存区有改动 → 取消暂存。"""
        if not self.status:
            return
        if src == "staged":
            self.unstage_paths([path])
            return
        entry = self.status.entry(path)
        if entry and entry.has_wt_changes:
            self.stage_paths([path])
        elif entry and entry.has_index_changes:
            self.unstage_paths([path])

    def stage_paths(self, paths: list[str]) -> None:
        """暂存指定文件（走 _mutate 后台管线，完成后 toast + 自动刷新）。"""
        self._mutate(gitbackend.stage, (paths,), f"暂存 {len(paths)} 个文件")

    def unstage_paths(self, paths: list[str]) -> None:
        """取消暂存指定文件。"""
        self._mutate(gitbackend.unstage, (paths,), f"取消暂存 {len(paths)} 个文件")

    def stage_all(self) -> None:
        """全部暂存（add -A）。"""
        self._mutate(gitbackend.stage_all, (), "全部暂存")

    def unstage_all(self) -> None:
        """全部取消暂存。"""
        self._mutate(gitbackend.unstage_all, (), "全部取消暂存")

    def action_stage_all(self) -> None:
        """全局 a 键入口（BINDINGS 要求 action_ 前缀方法）。"""
        self.stage_all()

    def action_unstage_all(self) -> None:
        """全局 u 键入口。"""
        self.unstage_all()

    # ---- mutations (git writes, run in threads) ---------------------------
    def _mutate(self, fn, args: tuple, desc: str) -> None:
        """所有"写仓库"操作的统一入口（stage/unstage/commit/push/pull/discard）。

        _busy 计数 +1 让状态栏显示 … 并暂停自动刷新；真正的 git 调用
        交给 _run_mutation 后台线程。desc 是操作描述，用于成功/失败 toast。
        """
        self._busy += 1
        if self.status:
            self.status_bar.update_status(self.status, busy=True)
        self._run_mutation(fn, args, desc)

    @work(thread=True, group="mutate")
    def _run_mutation(self, fn, args: tuple, desc: str) -> None:
        """后台执行写操作。gitbackend 抛出的 GitError（含 git stderr）
        和其他异常都转成 error 字符串，回主线程统一汇报。"""
        error: str | None = None
        detail = ""
        try:
            detail = fn(self.repo_path, *args) or ""
        except GitError as e:
            error = e.stderr or str(e)
        except Exception as e:  # noqa: BLE001
            error = str(e)
        self.call_from_thread(self._mutation_done, desc, detail, error)

    def _mutation_done(self, desc: str, detail: str, error: str | None) -> None:
        """写操作收尾（主线程）：弹 toast 汇报结果，然后刷新状态和 log。

        - 失败：红色 toast，错误信息截断到 400 字符（git stderr 可能很长）
        - 成功：优先显示 git 返回的 detail（如 push 输出），否则"xx完成"
        - markup=False：git 输出里的 [xxx] 不能被当成 rich 标记解析
        """
        self._busy = max(0, self._busy - 1)
        if error:
            self.notify(f"{desc}失败: {error[:400]}", severity="error",
                        timeout=10, markup=False)
        else:
            self.notify(detail.strip() or f"{desc}完成", timeout=5, markup=False)
        self.refresh_all()
        self.load_log()

    # ---- commit / push / pull ---------------------------------------------
    def action_commit(self) -> None:
        """c：打开提交弹窗。没有已暂存文件时直接警告，不弹窗。"""
        st = self.status
        if not st or not st.index_entries:
            self.notify("没有已暂存的文件 (Space 暂存)", severity="warning")
            return
        # push_screen 第二个参数是回调：弹窗 dismiss(message) 时触发
        self.push_screen(CommitModal(len(st.index_entries)), self._commit_callback)

    def _commit_callback(self, message: str | None) -> None:
        """提交弹窗回调：None = 用户取消；字符串 = commit message，走 _mutate 提交。"""
        if not message:
            return
        self._mutate(gitbackend.commit, (message,), "提交")

    def action_push(self) -> None:
        """P：推送当前分支。没有提交历史时警告（空仓库 push 无意义）。"""
        st = self.status
        if not st or not st.has_commits:
            self.notify("还没有提交，先按 c 提交", severity="warning")
            return
        self._mutate(gitbackend.push, (st.head,), "push")

    def action_pull(self) -> None:
        """p：拉取更新（--ff-only，有分叉时 git 会报错并经 toast 显示）。"""
        self._mutate(gitbackend.pull, (), "pull")

    # ---- misc ----------------------------------------------------------
    def toggle_tree_mode(self) -> None:
        """切换文件树"仅改动/全部文件"模式并触发刷新（"all" 模式下
        refresh_all 会额外调 list_all_files）。"""
        if not self.status:
            return
        self.tree_mode = "all" if self.tree_mode == "changes" else "changes"
        self.refresh_all()

    def action_toggle_tree_mode(self) -> None:
        """全局 t 键入口。"""
        self.toggle_tree_mode()

    def action_refresh(self) -> None:
        """全局 r 键：状态 + log 都强制刷新。"""
        self.refresh_all()
        self.load_log()

    def discard_request(self, src: str, path: str) -> None:
        """d：丢弃工作区改动的入口。先做可行性检查再弹确认框。

        - 未跟踪文件 → 走"删除文件"分支（git 无法恢复从未提交的内容）
        - 已跟踪且工作区有改动 → 走"恢复到最后一次提交"分支
        - 改动只在暂存区（工作区干净）→ 提示用户先 Space 取消暂存，
          因为 restore 只作用于工作区，此时没有可丢弃的东西
        """
        st = self.status
        entry = st.entry(path) if st else None
        if entry is None:
            return
        tracked: list[str] = []
        untracked: list[str] = []
        if entry.has_wt_changes:
            if entry.untracked:
                untracked = [path]
            else:
                tracked = [path]
        elif entry.has_index_changes:
            self.notify("该文件改动已暂存，工作区无改动 (Space 可取消暂存)")
            return
        else:
            return
        action_desc = "将删除未跟踪文件" if untracked else "将恢复到最后一次提交"
        # partial 把 tracked/untracked 预绑定进回调——确认弹窗本身只回 True/False
        self.push_screen(
            ConfirmModal(
                "丢弃改动?",
                [path, action_desc, "此操作不可撤销"],
            ),
            partial(self._discard_callback, tracked, untracked),
        )

    def _discard_callback(self, tracked: list[str], untracked: list[str], ok) -> None:
        """丢弃确认框回调：用户确认后走 _mutate（后台线程删/恢复文件）。"""
        if not ok:
            return
        self._mutate(
            lambda cwd: gitbackend.discard_worktree(cwd, tracked, untracked),
            (),
            "已丢弃改动",
        )

    def open_editor(self, path: str) -> None:
        """e：用 $EDITOR 打开文件并 toast 提示（编辑器独立进程，不阻塞 TUI）。"""
        gitbackend.open_editor(Path(self.repo_path) / path)
        self.notify(f"已在编辑器打开 {path}", timeout=3, markup=False)

    def action_help(self) -> None:
        """?：打开帮助弹窗。"""
        self.push_screen(HelpModal())

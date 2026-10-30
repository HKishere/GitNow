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
    TITLE = "GitNow"
    CSS_PATH = "gitnow.tcss"

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
        self.repo_path = repo_path
        self.status: RepoStatus | None = None
        self.selected: tuple[str, str] | None = None
        self.tree_mode = "changes"
        self.log_entries: list[LogEntry] = []
        self.log_complete = False
        self._busy = 0
        self._log_loading = False
        self._all_files: list[str] = []

    # ---- widgets ----------------------------------------------------------
    def compose(self) -> ComposeResult:
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield FileTreePanel(id="tree-panel")
                yield StagedPanel(id="staged-panel")
            yield RightViewer(id="viewer")
        yield StatusBar(id="statusbar")

    @property
    def tree_panel(self) -> FileTreePanel:
        return self.query_one("#tree-panel", FileTreePanel)

    @property
    def staged_panel(self) -> StagedPanel:
        return self.query_one("#staged-panel", StagedPanel)

    @property
    def viewer(self) -> RightViewer:
        return self.query_one("#viewer", RightViewer)

    @property
    def status_bar(self) -> StatusBar:
        return self.query_one("#statusbar", StatusBar)

    @property
    def focus_targets(self):
        viewer = self.viewer.log_list if self.viewer.mode == "log" else self.viewer
        return [self.tree_panel, self.staged_panel, viewer]

    # ---- lifecycle ----------------------------------------------------------
    def on_mount(self) -> None:
        self.tree_panel.border_title = RichText(" 文件树 ", style=f"bold {theme.ACCENT_BLUE}")
        self.staged_panel.border_title = RichText(" 已暂存 (staged) ", style=f"bold {theme.ACCENT_GREEN}")
        self.viewer.border_title = RichText(" log / diff ", style=f"bold {theme.ACCENT_ORANGE}")
        self.viewer.show_note("加载中…")
        self.status_bar.update_status(RepoStatus(head="…"))
        self.refresh_all()
        self.load_log()
        self.set_interval(3.0, self._auto_refresh)
        self.set_focus(self.tree_panel)

    def _auto_refresh(self) -> None:
        if self._busy or len(self.screen_stack) > 1:
            return
        self.refresh_all()

    # ---- refresh ----------------------------------------------------------
    @work(thread=True, group="refresh", exclusive=True)
    def refresh_all(self) -> None:
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
        self.status = st
        if all_files:
            self._all_files = all_files
        self.status_bar.update_status(st, busy=self._busy > 0)
        self.tree_panel.rebuild(
            st, self._all_files, self.tree_mode, keep_path=self.tree_panel.current_path
        )
        self.staged_panel.rebuild(st, keep_path=self.staged_panel.highlighted_path)
        if self.selected:
            entry = st.entry(self.selected[1])
            if entry is None or not (entry.has_index_changes or entry.has_wt_changes):
                self.selected = None
                self.viewer.token = None
        if self.selected is None and self.viewer.mode == "diff":
            self.viewer.populate_log(self.log_entries, self.log_complete)

    # ---- log ----------------------------------------------------------
    @work(thread=True, group="log", exclusive=True)
    def load_log(self, append: bool = False) -> None:
        skip = len(self.log_entries) if append else 0
        try:
            entries = gitbackend.log(self.repo_path, skip=skip)
        except Exception:  # noqa: BLE001
            entries = []
        self.call_from_thread(self._apply_log, entries, append)

    def _apply_log(self, entries: list[LogEntry], append: bool) -> None:
        self._log_loading = False
        if not append:
            self.log_entries = []
        self.log_entries.extend(entries)
        self.log_complete = len(entries) < gitbackend.LOG_PAGE
        if self.viewer.mode == "log" or (
            self.selected is None and self.viewer.mode != "commit"
        ):
            self.viewer.populate_log(self.log_entries, self.log_complete)

    def load_more_log(self) -> None:
        if self.log_complete or self._log_loading or self.viewer.mode != "log":
            return
        self._log_loading = True
        self.load_log(append=True)

    # ---- selection / diff ------------------------------------------------
    @on(FileHighlighted)
    def on_file_highlighted(self, event: FileHighlighted) -> None:
        self.set_selection(event.panel, event.path)

    def set_selection(self, panel: str, path: str) -> None:
        if self.selected == (panel, path):
            return
        self.selected = (panel, path)
        self.viewer.token = (panel, path)
        self.request_diff()

    @work(thread=True, group="diff", exclusive=True)
    def request_diff(self) -> None:
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
        if self.viewer.mode != "log":
            return
        self.viewer.token = ("commit", event.sha)
        self._fetch_commit(event.sha)

    @work(thread=True, group="diff", exclusive=True)
    def _fetch_commit(self, sha: str) -> None:
        try:
            text = gitbackend.show_commit(self.repo_path, sha)
        except GitError as e:
            text = f"(show 失败: {e.stderr})"
        self.call_from_thread(self.viewer.apply_commit, sha, text, ("commit", sha))

    @on(BackRequested)
    def _on_back(self, event: BackRequested) -> None:
        if self.viewer.mode == "commit":
            self._back_to_log()
        else:
            self.clear_selection()

    @on(LogNearEnd)
    def _on_log_near_end(self, event: LogNearEnd) -> None:
        self.load_more_log()

    def action_clear_selection(self) -> None:
        if len(self.screen_stack) > 1:
            return
        if self.viewer.mode == "commit":
            self._back_to_log()
        else:
            self.clear_selection()

    def _back_to_log(self) -> None:
        self.viewer.token = None
        self.viewer.populate_log(self.log_entries, self.log_complete)
        self._focus_log_list()

    def clear_selection(self) -> None:
        self.selected = None
        self.viewer.token = None
        self.viewer.populate_log(self.log_entries, self.log_complete)
        self._focus_log_list()

    def _focus_log_list(self) -> None:
        log_list = self.viewer.log_list
        if log_list.display and not log_list.has_focus:
            log_list.focus()

    # ---- focus ----------------------------------------------------------
    def action_cycle_focus(self) -> None:
        if len(self.screen_stack) > 1:
            return
        targets = self.focus_targets
        try:
            idx = targets.index(self.focused)
        except ValueError:
            idx = -1
        targets[(idx + 1) % len(targets)].focus()

    def action_cycle_focus_back(self) -> None:
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
        self._mutate(gitbackend.stage, (paths,), f"暂存 {len(paths)} 个文件")

    def unstage_paths(self, paths: list[str]) -> None:
        self._mutate(gitbackend.unstage, (paths,), f"取消暂存 {len(paths)} 个文件")

    def stage_all(self) -> None:
        self._mutate(gitbackend.stage_all, (), "全部暂存")

    def unstage_all(self) -> None:
        self._mutate(gitbackend.unstage_all, (), "全部取消暂存")

    def action_stage_all(self) -> None:
        self.stage_all()

    def action_unstage_all(self) -> None:
        self.unstage_all()

    # ---- mutations (git writes, run in threads) ---------------------------
    def _mutate(self, fn, args: tuple, desc: str) -> None:
        self._busy += 1
        if self.status:
            self.status_bar.update_status(self.status, busy=True)
        self._run_mutation(fn, args, desc)

    @work(thread=True, group="mutate")
    def _run_mutation(self, fn, args: tuple, desc: str) -> None:
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
        st = self.status
        if not st or not st.index_entries:
            self.notify("没有已暂存的文件 (Space 暂存)", severity="warning")
            return
        self.push_screen(CommitModal(len(st.index_entries)), self._commit_callback)

    def _commit_callback(self, message: str | None) -> None:
        if not message:
            return
        self._mutate(gitbackend.commit, (message,), "提交")

    def action_push(self) -> None:
        st = self.status
        if not st or not st.has_commits:
            self.notify("还没有提交，先按 c 提交", severity="warning")
            return
        self._mutate(gitbackend.push, (st.head,), "push")

    def action_pull(self) -> None:
        self._mutate(gitbackend.pull, (), "pull")

    # ---- misc ----------------------------------------------------------
    def toggle_tree_mode(self) -> None:
        if not self.status:
            return
        self.tree_mode = "all" if self.tree_mode == "changes" else "changes"
        self.refresh_all()

    def action_toggle_tree_mode(self) -> None:
        self.toggle_tree_mode()

    def action_refresh(self) -> None:
        self.refresh_all()
        self.load_log()

    def discard_request(self, src: str, path: str) -> None:
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
        self.push_screen(
            ConfirmModal(
                "丢弃改动?",
                [path, action_desc, "此操作不可撤销"],
            ),
            partial(self._discard_callback, tracked, untracked),
        )

    def _discard_callback(self, tracked: list[str], untracked: list[str], ok) -> None:
        if not ok:
            return
        self._mutate(
            lambda cwd: gitbackend.discard_worktree(cwd, tracked, untracked),
            (),
            "已丢弃改动",
        )

    def open_editor(self, path: str) -> None:
        gitbackend.open_editor(Path(self.repo_path) / path)
        self.notify(f"已在编辑器打开 {path}", timeout=3, markup=False)

    def action_help(self) -> None:
        self.push_screen(HelpModal())

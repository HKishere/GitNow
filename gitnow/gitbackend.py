"""All git access goes through this module: subprocess only, no libgit2.

Conventions:
- every invocation gets -c core.quotepath=false (CJK filenames) and cat pagers
- output decoded as utf-8 with errors='replace'
- user-supplied paths passed to pathspec-aware commands are wrapped with
  :(literal) so characters like '[' never act as globs
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .models import FileEntry, LogEntry, RepoStatus

# git log 的输出格式：完整SHA 短SHA 作者 日期 refs 标题，列间用 \t 分隔。
# %d 是装饰（分支/tag），可能为空但列仍在，保证 split("\t") 列数固定。
LOG_FORMAT = "%H%x09%h%x09%an%x09%ad%x09%d%x09%s"
DATE_FORMAT = "%Y-%m-%d %H:%M"  # log 列表显示的日期格式
LOG_PAGE = 200        # log 每次分页加载的条数（滚动到底部附近再加载下一页）
MAX_DIFF_LINES = 5000  # diff/commit 详情最多渲染的行数，超出截断（防止大 diff 卡死 UI）


class GitError(Exception):
    """git 命令执行失败时抛出，携带完整命令、退出码和 stderr，方便 UI 层展示。"""

    def __init__(self, args: list[str], returncode: int, stderr: str):
        self.args_list = args            # 出错的那条 git 子命令（不含 git 本体）
        self.returncode = returncode     # git 的退出码
        self.stderr = (stderr or "").strip()  # 错误输出（git 的诊断信息都在 stderr）
        super().__init__(f"git {' '.join(args)} -> {returncode}: {self.stderr}")


def _base_env() -> dict:
    """构造子进程环境变量。

    - GIT_PAGER/PAGER=cat：git 某些命令可能调起交互式分页器，在子进程里会挂死，
      强制用 cat 让输出一次性写完
    - GIT_OPTIONAL_LOCKS=0：禁用可选锁，避免只读命令在仓库里产生 index.lock 副作用
    """
    env = dict(os.environ)
    env["GIT_PAGER"] = "cat"
    env["PAGER"] = "cat"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    return env


def git(
    *args: str,
    cwd: str | Path,
    allow_fail: bool = False,
    timeout: int = 60,
) -> subprocess.CompletedProcess:
    """执行一条 git 子命令，返回 CompletedProcess。

    - 前置 -c 参数保证输出稳定：core.quotepath=false 让中文文件名不转义成
      "\\\\xxx" 八进制；pager/color 全关，拿到的就是纯文本
    - allow_fail=True 时失败不抛异常（调用方自己看 returncode），
      用于"探测型"命令（is_repo/has_commits/各种 diff）
    - timeout 到点抛 subprocess.TimeoutExpired，防止网络类操作卡死后台线程
    """
    cmd = [
        "git",
        "-c", "core.quotepath=false",
        "-c", "core.pager=cat",
        "-c", "color.ui=false",
        *args,
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=_base_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",  # 仓库里可能有非 UTF-8 文件名/内容，替换坏字节而不是崩
        timeout=timeout,
    )
    if proc.returncode != 0 and not allow_fail:
        raise GitError(args, proc.returncode, proc.stderr)
    return proc


def _lit(path: str) -> str:
    """Wrap a repo-relative path as a literal pathspec.

    :(literal) 前缀让 git 把路径当纯字面量处理——否则文件名里的
    '[' '*' '?' 等字符会被 git 当 glob 通配符解释，导致 add/diff 错文件。
    """
    return f":(literal){path}"


def is_repo(cwd: str | Path) -> bool:
    """判断目录是否位于一个 git 工作区内（启动入口用它校验参数）。"""
    proc = git("rev-parse", "--is-inside-work-tree", cwd=cwd, allow_fail=True)
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def has_commits(cwd: str | Path) -> bool:
    """仓库是否已有至少一次提交（空仓库 HEAD 不存在，rev-parse HEAD 会失败）。"""
    proc = git("rev-parse", "--verify", "HEAD", cwd=cwd, allow_fail=True)
    return proc.returncode == 0


def status(cwd: str | Path) -> RepoStatus:
    """解析 `git status --porcelain=v2 --branch -z`，产出 RepoStatus。

    porcelain v2 的记录类型：
      # branch.*  分支元信息（head/oid/upstream/ahead-behind）
      1 XY ...    普通改动记录，第 9 列是路径
      2 XY ...    重命名/拷贝记录，路径列之后紧跟一行原路径（-z 模式下用 \0 分隔）
      u XY ...    合并冲突记录，第 12 列是路径
      ? path      未跟踪文件
    用 -z（NUL 分隔）而不是换行，因为文件名可以包含换行符。

    解析逻辑：手动推进游标 i，遇到 "2 " 记录时多消费一条（原路径）；
    其余记录各取自己的固定列。任何解析失败都静默跳过，不让 UI 崩。
    """
    proc = git("status", "--porcelain=v2", "--branch", "-z", "--untracked-files=all",
               cwd=cwd, allow_fail=True)
    st = RepoStatus()
    if proc.returncode != 0:
        return st  # 不是仓库或 git 出错时返回空状态，由调用方处理
    records = proc.stdout.split("\0")
    i = 0
    while i < len(records):
        rec = records[i]
        i += 1
        if not rec:
            continue
        if rec.startswith("# branch.head "):
            # 当前分支名；detached HEAD 时 git 输出 "(detached)"
            value = rec[len("# branch.head "):]
            if value == "(detached)":
                st.head_detached = True
                st.head = "(detached)"
            else:
                st.head = value
        elif rec.startswith("# branch.oid "):
            # HEAD 指向的 SHA；空仓库输出 "(initial)"
            st.head_oid = rec.split(" ", 2)[2]
            st.has_commits = st.head_oid != "(initial)"
        elif rec.startswith("# branch.upstream "):
            st.upstream = rec.split(" ", 2)[2]
        elif rec.startswith("# branch.ab "):
            # ahead/behind 计数，形如 "+2 -1"
            for tok in rec.split(" ", 2)[2].split():
                if tok.startswith("+"):
                    st.ahead = int(tok[1:] or 0)
                elif tok.startswith("-"):
                    st.behind = int(tok[1:] or 0)
        elif rec.startswith("1 "):
            # 普通改动：1 XY sub mH mI mW hH hI path（共 9 列，路径是最后一列，
            # 因此 split 限 8 次——路径本身可以含空格）
            parts = rec.split(" ", 8)
            if len(parts) == 9:
                st.entries.append(FileEntry(path=parts[8], xy=parts[1]))
        elif rec.startswith("2 "):
            # 重命名：格式同 "1 "，但路径后面在 -z 流里紧跟下一条记录=原路径
            parts = rec.split(" ", 8)
            if len(parts) == 9:
                orig = records[i] if i < len(records) else None
                i += 1  # 额外消费一条：原路径
                st.entries.append(FileEntry(path=parts[8], xy=parts[1], renamed_from=orig))
        elif rec.startswith("u "):
            # 冲突：u XY sub m1 m2 m3 mW h1 h2 h3 path（共 12 列）
            parts = rec.split(" ", 11)
            if len(parts) == 12:
                st.entries.append(FileEntry(path=parts[11], xy=parts[1]))
        elif rec.startswith("? "):
            st.entries.append(FileEntry(path=rec[2:], xy="??"))
    return st


def list_all_files(cwd: str | Path) -> list[str]:
    """列出仓库所有文件（已跟踪 + 未跟踪，应用 .gitignore 排除）。

    只在"树模式=全部文件"时调用，用于把无改动的文件也显示进文件树（灰色）。
    """
    proc = git("ls-files", "-z", "--cached", "--others", "--exclude-standard", cwd=cwd)
    seen: set[str] = set()
    files: list[str] = []
    for line in proc.stdout.split("\0"):
        if line and line not in seen:
            seen.add(line)
            files.append(line)
    return sorted(files)


def diff_worktree(cwd: str | Path, path: str) -> str:
    """工作区 vs 暂存区的 diff（右侧面板"工作区"徽章）。

    allow_fail=True：对新文件等场景 diff 可能返回非 0，此时把 stdout（可能为空）原样给 UI。
    """
    proc = git("--no-pager", "diff", "--no-color", "-U3", "--", _lit(path),
               cwd=cwd, allow_fail=True)
    return proc.stdout


def diff_cached(cwd: str | Path, path: str) -> str:
    """暂存区 vs HEAD 的 diff（右侧面板"已暂存"徽章）。"""
    proc = git("--no-pager", "diff", "--cached", "--no-color", "-U3", "--", _lit(path),
               cwd=cwd, allow_fail=True)
    return proc.stdout


def diff_untracked(cwd: str | Path, path: str) -> str:
    """Diff an untracked file against the empty tree.

    `git diff --no-index` exits 1 when there are differences; allow_fail covers
    that. If git cannot produce output (e.g. odd device paths), fall back to a
    synthesized all-added diff.
    """
    proc = git("--no-pager", "diff", "--no-index", "--no-color", "-U3",
               "--", "/dev/null", path, cwd=cwd, allow_fail=True)
    if proc.stdout.strip():
        return proc.stdout
    # 兜底：git --no-index 偶尔出不了输出（设备文件等），手工伪造一份
    # "全部新增"的 diff，至少让用户能看文件内容。
    try:
        text = (Path(cwd) / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return f"(无法读取文件: {path})"
    lines = text.splitlines()
    out = [f"diff --git a/{path} b/{path}", "--- /dev/null", f"+++ b/{path}"]
    out.append(f"@@ -0,0 +1,{max(len(lines), 1)} @@")
    out += ["+" + ln for ln in lines]
    return "\n".join(out)


def log(cwd: str | Path, limit: int = LOG_PAGE, skip: int = 0) -> list[LogEntry]:
    """分页读取 git log（右侧 log 列表 + 无限滚动）。

    skip=已加载条数，实现"滚动到底再加载下一页"；按 LOG_FORMAT 输出，
    逐行按 \t 拆成 6 列。refs 列外层的括号（git 原样输出 "(HEAD -> master)"）
    去掉后再存，渲染时自己加高亮。
    """
    proc = git(
        "--no-pager", "log",
        f"--max-count={limit}", f"--skip={skip}",
        f"--date=format-local:{DATE_FORMAT}",
        f"--pretty=format:{LOG_FORMAT}",
        cwd=cwd, allow_fail=True,
    )
    entries: list[LogEntry] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t", 5)  # 限 5 次：subject 里可以有 \t
        if len(parts) != 6:
            continue
        sha, short, author, date, refs, subject = parts
        refs = refs.strip()
        if refs.startswith("(") and refs.endswith(")"):
            refs = refs[1:-1]
        entries.append(LogEntry(sha=sha, short=short, author=author,
                                date=date, subject=subject, refs=refs))
    return entries


def show_commit(cwd: str | Path, sha: str) -> str:
    """读取单个提交的完整信息（--stat 摘要 + --patch 全部补丁），用于提交详情视图。

    大提交可能输出很大，timeout 放宽到 120s；行数截断由 UI 层（MAX_DIFF_LINES）负责。
    """
    proc = git("--no-pager", "show", "--no-color", "--stat", "--patch", "-U3", sha,
               cwd=cwd, timeout=120)
    return proc.stdout


def stage(cwd: str | Path, paths: list[str]) -> None:
    """暂存指定文件（git add -- <paths>，路径加 :(literal) 防通配符注入）。"""
    git("add", "--", *(_lit(p) for p in paths), cwd=cwd)


def stage_all(cwd: str | Path) -> None:
    """暂存全部改动（git add -A：含修改、删除、未跟踪）。"""
    git("add", "-A", cwd=cwd)


def unstage(cwd: str | Path, paths: list[str]) -> None:
    """取消暂存指定文件（restore --staged 只动 index，不碰工作区内容）。"""
    git("restore", "--staged", "--", *(_lit(p) for p in paths), cwd=cwd)


def unstage_all(cwd: str | Path) -> None:
    """取消全部暂存。

    有提交历史时用 `git reset`（混合同步 index 到 HEAD，保留工作区改动）；
    空仓库 HEAD 不存在，reset 会失败，改用 `git rm --cached -r .`
    把所有文件从 index 里移出（文件本身留在磁盘上，仍是未跟踪状态）。
    """
    if has_commits(cwd):
        git("reset", "--quiet", cwd=cwd)
    else:
        git("rm", "--cached", "-r", "--quiet", ".", cwd=cwd, allow_fail=True)


def discard_worktree(cwd: str | Path, tracked: list[str], untracked: list[str]) -> None:
    """丢弃工作区改动（不可恢复，UI 层必须先弹 ConfirmModal）。

    - tracked：`git restore --` 把文件内容恢复到 HEAD/index 版本
    - untracked：git 无法恢复"从未提交"的文件，直接 unlink 删除；
      删完后逐级向上尝试 rmdir 清理变空的父目录（rmdir 只删空目录，
      非空会抛 OSError，正好作为"停止向上清理"的信号）
    """
    if tracked:
        git("restore", "--", *(_lit(p) for p in tracked), cwd=cwd)
    root = Path(cwd)
    for p in untracked:
        fp = root / p
        try:
            fp.unlink()
        except OSError:
            continue
        parent = fp.parent
        while parent != root:
            try:
                parent.rmdir()  # only removes when empty
            except OSError:
                break
            parent = parent.parent


def commit(cwd: str | Path, message: str) -> str:
    """提交暂存区，返回 git 的输出文本（供 toast 显示，失败抛 GitError）。"""
    proc = git("commit", "-m", message, cwd=cwd)
    return (proc.stdout or proc.stderr).strip()


def has_origin(cwd: str | Path) -> bool:
    """是否配置了至少一个 remote（push 失败时决定要不要尝试 --set-upstream）。"""
    return bool(git("remote", cwd=cwd).stdout.strip())


def push(cwd: str | Path, branch: str) -> str:
    """推送当前分支，带"无 upstream 自动补设"的恢复逻辑。

    git push 的诊断信息走 stderr，所以成功消息也从 stderr 取。
    失败且 stderr 含 "no upstream" 时：若配置了 remote，自动用
    `push --set-upstream origin <branch>` 重试一次（首次推送新分支的常见情况）；
    重试仍失败或没有 remote，则抛 GitError 交给 UI 层 toast。
    """
    proc = git("push", cwd=cwd, allow_fail=True, timeout=180)
    if proc.returncode == 0:
        return (proc.stderr or proc.stdout).strip() or "push 完成"
    err = proc.stderr
    if "no upstream" in err and has_origin(cwd):
        proc2 = git("push", "--set-upstream", "origin", branch,
                    cwd=cwd, allow_fail=True, timeout=180)
        if proc2.returncode == 0:
            return "push 完成 (已建立 upstream)"
        raise GitError(["push", "--set-upstream"], proc2.returncode, proc2.stderr)
    raise GitError(["push"], proc.returncode, err)


def pull(cwd: str | Path) -> str:
    """拉取更新，--ff-only 拒绝产生合并提交（有分叉时报错让用户自己处理）。"""
    proc = git("pull", "--ff-only", cwd=cwd, timeout=180)
    return (proc.stderr or proc.stdout).strip() or "已是最新"


def fetch(cwd: str | Path) -> str:
    """从远程获取更新（只下载，不合并，不改动工作区）。

    git fetch 的进度/结果输出走 stderr，所以成功消息也从 stderr 取。
    与 pull 的区别：fetch 只更新远程跟踪分支，不会改动当前工作区和 HEAD。
    """
    proc = git("fetch", cwd=cwd, timeout=180)
    return (proc.stderr or proc.stdout).strip() or "fetch 完成"


def open_editor(path: str | Path) -> None:
    """用 $EDITOR/$VISUAL（缺省 notepad）打开文件；Popen 不等待编辑器退出。"""
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "notepad"
    subprocess.Popen([editor, str(path)])

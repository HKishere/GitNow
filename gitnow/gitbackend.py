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

LOG_FORMAT = "%H%x09%h%x09%an%x09%ad%x09%d%x09%s"
DATE_FORMAT = "%Y-%m-%d %H:%M"
LOG_PAGE = 200
MAX_DIFF_LINES = 5000


class GitError(Exception):
    def __init__(self, args: list[str], returncode: int, stderr: str):
        self.args_list = args
        self.returncode = returncode
        self.stderr = (stderr or "").strip()
        super().__init__(f"git {' '.join(args)} -> {returncode}: {self.stderr}")


def _base_env() -> dict:
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
        errors="replace",
        timeout=timeout,
    )
    if proc.returncode != 0 and not allow_fail:
        raise GitError(args, proc.returncode, proc.stderr)
    return proc


def _lit(path: str) -> str:
    """Wrap a repo-relative path as a literal pathspec."""
    return f":(literal){path}"


def is_repo(cwd: str | Path) -> bool:
    proc = git("rev-parse", "--is-inside-work-tree", cwd=cwd, allow_fail=True)
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def has_commits(cwd: str | Path) -> bool:
    proc = git("rev-parse", "--verify", "HEAD", cwd=cwd, allow_fail=True)
    return proc.returncode == 0


def status(cwd: str | Path) -> RepoStatus:
    proc = git("status", "--porcelain=v2", "--branch", "-z", "--untracked-files=all",
               cwd=cwd, allow_fail=True)
    st = RepoStatus()
    if proc.returncode != 0:
        return st
    records = proc.stdout.split("\0")
    i = 0
    while i < len(records):
        rec = records[i]
        i += 1
        if not rec:
            continue
        if rec.startswith("# branch.head "):
            value = rec[len("# branch.head "):]
            if value == "(detached)":
                st.head_detached = True
                st.head = "(detached)"
            else:
                st.head = value
        elif rec.startswith("# branch.oid "):
            st.head_oid = rec.split(" ", 2)[2]
            st.has_commits = st.head_oid != "(initial)"
        elif rec.startswith("# branch.upstream "):
            st.upstream = rec.split(" ", 2)[2]
        elif rec.startswith("# branch.ab "):
            for tok in rec.split(" ", 2)[2].split():
                if tok.startswith("+"):
                    st.ahead = int(tok[1:] or 0)
                elif tok.startswith("-"):
                    st.behind = int(tok[1:] or 0)
        elif rec.startswith("1 "):
            parts = rec.split(" ", 8)
            if len(parts) == 9:
                st.entries.append(FileEntry(path=parts[8], xy=parts[1]))
        elif rec.startswith("2 "):
            parts = rec.split(" ", 8)
            if len(parts) == 9:
                orig = records[i] if i < len(records) else None
                i += 1
                st.entries.append(FileEntry(path=parts[8], xy=parts[1], renamed_from=orig))
        elif rec.startswith("u "):
            parts = rec.split(" ", 11)
            if len(parts) == 12:
                st.entries.append(FileEntry(path=parts[11], xy=parts[1]))
        elif rec.startswith("? "):
            st.entries.append(FileEntry(path=rec[2:], xy="??"))
    return st


def list_all_files(cwd: str | Path) -> list[str]:
    proc = git("ls-files", "-z", "--cached", "--others", "--exclude-standard", cwd=cwd)
    seen: set[str] = set()
    files: list[str] = []
    for line in proc.stdout.split("\0"):
        if line and line not in seen:
            seen.add(line)
            files.append(line)
    return sorted(files)


def diff_worktree(cwd: str | Path, path: str) -> str:
    proc = git("--no-pager", "diff", "--no-color", "-U3", "--", _lit(path),
               cwd=cwd, allow_fail=True)
    return proc.stdout


def diff_cached(cwd: str | Path, path: str) -> str:
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
    proc = git(
        "--no-pager", "log",
        f"--max-count={limit}", f"--skip={skip}",
        f"--date=format-local:{DATE_FORMAT}",
        f"--pretty=format:{LOG_FORMAT}",
        cwd=cwd, allow_fail=True,
    )
    entries: list[LogEntry] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t", 5)
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
    proc = git("--no-pager", "show", "--no-color", "--stat", "--patch", "-U3", sha,
               cwd=cwd, timeout=120)
    return proc.stdout


def stage(cwd: str | Path, paths: list[str]) -> None:
    git("add", "--", *(_lit(p) for p in paths), cwd=cwd)


def stage_all(cwd: str | Path) -> None:
    git("add", "-A", cwd=cwd)


def unstage(cwd: str | Path, paths: list[str]) -> None:
    git("restore", "--staged", "--", *(_lit(p) for p in paths), cwd=cwd)


def unstage_all(cwd: str | Path) -> None:
    if has_commits(cwd):
        git("reset", "--quiet", cwd=cwd)
    else:
        git("rm", "--cached", "-r", "--quiet", ".", cwd=cwd, allow_fail=True)


def discard_worktree(cwd: str | Path, tracked: list[str], untracked: list[str]) -> None:
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
    proc = git("commit", "-m", message, cwd=cwd)
    return (proc.stdout or proc.stderr).strip()


def has_origin(cwd: str | Path) -> bool:
    return bool(git("remote", cwd=cwd).stdout.strip())


def push(cwd: str | Path, branch: str) -> str:
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
    proc = git("pull", "--ff-only", cwd=cwd, timeout=180)
    return (proc.stderr or proc.stdout).strip() or "已是最新"


def open_editor(path: str | Path) -> None:
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "notepad"
    subprocess.Popen([editor, str(path)])

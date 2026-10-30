"""Data models shared across GitNow."""

from __future__ import annotations

from dataclasses import dataclass, field

CONFLICT_XY = {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}


@dataclass
class FileEntry:
    """One path as reported by `git status --porcelain=v2`.

    xy is the 2-char XY code: index status + worktree status,
    '.' means no change, '??' means untracked, 'UU' etc. means conflict.
    """

    path: str
    xy: str = ".."
    renamed_from: str | None = None

    def __post_init__(self) -> None:
        self.xy = (self.xy or "..").replace(" ", ".")

    @property
    def untracked(self) -> bool:
        return self.xy == "??"

    @property
    def unmerged(self) -> bool:
        return self.xy in CONFLICT_XY

    @property
    def index_status(self) -> str:
        return self.xy[0]

    @property
    def wt_status(self) -> str:
        return self.xy[1]

    @property
    def has_index_changes(self) -> bool:
        return not self.untracked and self.xy[0] != "."

    @property
    def has_wt_changes(self) -> bool:
        return self.untracked or self.xy[1] != "."

    @property
    def wt_letter(self) -> str:
        return "?" if self.untracked else self.wt_status

    @property
    def index_letter(self) -> str:
        return "A" if self.untracked else self.index_status


@dataclass
class LogEntry:
    sha: str
    short: str
    author: str
    date: str
    subject: str
    refs: str = ""


@dataclass
class RepoStatus:
    head: str = ""
    head_detached: bool = False
    head_oid: str = ""
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0
    has_commits: bool = True
    entries: list[FileEntry] = field(default_factory=list)

    def entry(self, path: str) -> FileEntry | None:
        for e in self.entries:
            if e.path == path:
                return e
        return None

    @property
    def worktree_entries(self) -> list[FileEntry]:
        return [e for e in self.entries if e.has_wt_changes]

    @property
    def index_entries(self) -> list[FileEntry]:
        return [e for e in self.entries if e.has_index_changes]

    @property
    def signature(self) -> str:
        parts = [self.head, str(self.ahead), str(self.behind)]
        parts += [f"{e.xy}:{e.path}" for e in self.entries]
        return "|".join(parts)

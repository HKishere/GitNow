from __future__ import annotations

import sys
from pathlib import Path

from . import gitbackend


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    path = Path(args[0]).resolve() if args else Path.cwd()
    if not gitbackend.is_repo(path):
        print(f"错误: {path} 不是 git 仓库")
        return 1
    from .app import GitNowApp

    GitNowApp(repo_path=str(path)).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""GitNow 命令行入口：校验仓库 → 启动 TUI。"""

from __future__ import annotations

import sys
from pathlib import Path

from . import gitbackend


def main(argv: list[str] | None = None) -> int:
    """程序主入口（pyproject 的 [project.scripts] 指向这里）。

    流程：取命令行第一个参数作为仓库路径（缺省用当前目录）→
    校验是 git 工作区（不是就打印错误返回 1）→ 延迟导入并启动 App。
    延迟导入 app 是为了：不是仓库时能快速失败，不用加载整个 TUI。
    返回值作为进程退出码。
    """
    args = list(sys.argv[1:] if argv is None else argv)
    path = Path(args[0]).resolve() if args else Path.cwd()
    if not gitbackend.is_repo(path):
        print(f"错误: {path} 不是 git 仓库")
        return 1
    from .app import GitNowApp

    GitNowApp(repo_path=str(path)).run()  # .run() 进入事件循环，阻塞到用户退出
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
